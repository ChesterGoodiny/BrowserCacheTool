from __future__ import annotations

import sys
import tkinter.messagebox as messagebox

from gui import is_admin, run


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("This application supports Windows only.")
    if not is_admin():
        messagebox.showerror("Недостаточно прав", "Для работы программы требуются права администратора.")
        raise SystemExit(1)
    run()