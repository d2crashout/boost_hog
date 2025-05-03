# gui.py

import threading
import tkinter as tk

class DebugGUI:
    def __init__(self, title="Bot Debug"):
        self.debug_logging = False  # Default state
        self._var = None
        self._start_gui(title)

    def _start_gui(self, title):
        def gui_loop():
            root = tk.Tk()
            root.title(title)
            root.geometry("200x80")

            self._var = tk.BooleanVar(value=self.debug_logging)

            def on_toggle():
                self.debug_logging = self._var.get()

            cb = tk.Checkbutton(
                root,
                text="Debug Logging",
                variable=self._var,
                command=on_toggle
            )
            cb.pack(pady=20)
            root.mainloop()

        threading.Thread(target=gui_loop, daemon=True).start()

    def is_debug_enabled(self):
        return self.debug_logging
