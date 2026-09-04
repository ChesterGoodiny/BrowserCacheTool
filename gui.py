from __future__ import annotations

import ctypes
import logging
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import operations
from logger import create_logger, log_path
from paths import BrowserSpec, browser_specs


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.logger = create_logger()
        self.busy = False
        self.clean_var = tk.BooleanVar(value=False)
        self.browser_list = browser_specs()
        self.browser_var = tk.StringVar(value=self.browser_list[0].label)
        self.root.title("Browser Cache Tool")
        self.root.geometry("760x560")
        self.root.minsize(650, 430)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Браузер:").pack(anchor="w")
        browser_box = ttk.Combobox(
            frame,
            textvariable=self.browser_var,
            values=[spec.label for spec in self.browser_list],
            state="readonly",
        )
        browser_box.pack(fill="x", pady=(0, 6))
        browser_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_status())
        self.path_label = ttk.Label(frame, text="")
        self.path_label.pack(anchor="w", pady=(0, 10))
        self._update_path_label()

        admin_text = "Права администратора: OK" if is_admin() else "Права администратора: НЕТ"
        self.admin_label = ttk.Label(frame, text=admin_text)
        self.admin_label.pack(anchor="w", pady=(0, 8))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(0, 10))
        self.lock_button = ttk.Button(buttons, text="Заблокировать кэш", command=lambda: self.start_operation("lock"))
        self.lock_button.pack(side="left", padx=(0, 6))
        self.unlock_button = ttk.Button(buttons, text="Разблокировать кэш", command=lambda: self.start_operation("unlock"))
        self.unlock_button.pack(side="left", padx=(0, 6))
        self.refresh_button = ttk.Button(buttons, text="Обновить статус", command=self.refresh_status)
        self.refresh_button.pack(side="left")
        self.log_button = ttk.Button(buttons, text="Открыть лог", command=self.open_log)
        self.log_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            frame,
            text="Очищать содержимое кэш-папок при блокировке",
            variable=self.clean_var,
        ).pack(anchor="w", pady=(0, 8))

        warning = "Операция работает только с кэшем выбранного браузера. IndexedDB и данные сайтов не затрагиваются."
        ttk.Label(frame, text=warning, wraplength=720).pack(anchor="w", pady=(0, 8))

        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=("browser", "profile", "folder", "status"), show="headings")
        for column, title, width in (("browser", "Браузер", 150), ("profile", "Профиль", 180), ("folder", "Папка", 180), ("status", "Статус", 180)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(frame, text=f"Лог: {log_path()}").pack(anchor="w", pady=(8, 0))
        self.status_label = ttk.Label(frame, text="Готово")
        self.status_label.pack(anchor="w")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.lock_button, self.unlock_button, self.refresh_button, self.log_button):
            button.configure(state=state)

    def open_log(self) -> None:
        subprocess.Popen(["explorer.exe", "/select,", str(log_path())], shell=False)

    def selected_browser(self) -> BrowserSpec:
        return next(spec for spec in self.browser_list if spec.label == self.browser_var.get())

    def _update_path_label(self) -> None:
        self.path_label.configure(text=f"Папка данных: {self.selected_browser().data_root}")

    def start_operation(self, mode: str) -> None:
        if self.busy:
            return
        if not is_admin():
            messagebox.showerror("Недостаточно прав", "Для работы программы требуются права администратора.")
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Перед выполнением операции {self.selected_browser().label} будет принудительно закрыт.\n"
            "Сохраните данные в открытых вкладках. Продолжить?",
        ):
            return
        self._set_busy(True)
        self._update_path_label()
        self.status_label.configure(text="Выполняется операция...")
        threading.Thread(
            target=self._operation_worker,
            args=(mode, self.selected_browser(), self.clean_var.get()),
            daemon=True,
        ).start()

    def _operation_worker(self, mode: str, spec: BrowserSpec, clean_before_lock: bool) -> None:
        try:
            summary = operations.run_operation(
                mode,
                spec,
                self.logger,
                clean_before_lock=clean_before_lock,
            )
            self.root.after(0, lambda: self._operation_done(summary))
        except Exception:
            self.logger.exception("Unexpected operation failure")
            self.root.after(0, lambda: self._operation_done(operations.Summary(errors=1)))

    def _operation_done(self, summary: operations.Summary) -> None:
        self._set_busy(False)
        self.refresh_status()
        self.status_label.configure(
            text=f"Выполнено успешно: {summary.success}; предупреждения: {summary.warnings}; ошибки: {summary.errors}"
        )
        if summary.errors:
            messagebox.showwarning("Операция завершена с ошибками", f"Подробности записаны в лог:\n{log_path()}")

    def refresh_status(self) -> None:
        if self.busy:
            return
        try:
            self._update_path_label()
            spec = self.selected_browser()
            rows = operations.collect_status(spec, self.logger)
            for item in self.tree.get_children():
                self.tree.delete(item)
            for row in rows:
                self.tree.insert("", "end", values=(spec.label, *row))
            if not rows:
                self.status_label.configure(text=f"Профили {spec.label} не найдены")
        except Exception:
            self.logger.exception("Status refresh failed")
            self.status_label.configure(text="Не удалось обновить статус")


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()