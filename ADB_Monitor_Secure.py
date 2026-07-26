import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import time
import re
import os
import platform
import datetime
import shutil
from dataclasses import dataclass
from typing import Optional, Tuple, List


@dataclass
class DeviceStats:
    """Структура данных статистики устройства"""
    phone: str
    version: str
    bootloader: str
    cpu: str
    ram: str
    storage: str
    battery: str
    display: str


class ADBExecutor:
    """
    Безопасное выполнение ADB команд.
    Ключевое отличие от оригинала: НИКАКОГО shell=True и НИКАКОЙ конкатенации строк.
    Все аргументы передаются списком — инъекции команд невозможны.
    """

    def __init__(self):
        self.adb_path = self._find_adb()
        self._prev_cpu_total = 0
        self._prev_cpu_idle = 0

    def _find_adb(self) -> Optional[str]:
        """Поиск adb в PATH и стандартных директориях"""
        adb_name = "adb.exe" if platform.system() == "Windows" else "adb"

        # 1. Проверяем PATH
        adb_in_path = shutil.which(adb_name)
        if adb_in_path:
            return adb_in_path

        # 2. Стандартные пути
        possible_paths = []
        if platform.system() == "Windows":
            possible_paths.extend([
                os.path.join(os.environ.get('ProgramFiles', ''), 'Android', 'platform-tools', 'adb.exe'),
                os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Android', 'platform-tools', 'adb.exe'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Android', 'Sdk', 'platform-tools', 'adb.exe'),
                os.path.join(os.getcwd(), 'adb.exe'),
                os.path.join(os.getcwd(), 'platform-tools', 'adb.exe'),
            ])
        else:
            possible_paths.extend([
                '/usr/bin/adb',
                '/usr/local/bin/adb',
                os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
                os.path.join(os.getcwd(), 'adb'),
            ])

        for path in possible_paths:
            if os.path.isfile(path):
                return path
        return None

    def is_available(self) -> bool:
        return self.adb_path is not None

    def run(self, args: List[str], timeout: int = 5) -> Tuple[Optional[str], Optional[str]]:
        """
        Выполнить ADB команду.
        :param args: список аргументов ПОСЛЕ 'adb' (например, ["devices"] -> adb devices)
        :return: (stdout, error_message)
        """
        if not self.adb_path:
            return None, "ADB не найден. Установите Android Platform Tools."

        full_args = [self.adb_path] + args
        try:
            result = subprocess.run(
                full_args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout
            )
            # Если stderr непустой И команда завершилась с ошибкой — возвращаем как ошибку
            if result.returncode != 0 and result.stderr.strip():
                return result.stdout.strip(), result.stderr.strip()
            return result.stdout.strip(), None
        except subprocess.TimeoutExpired:
            return None, "⏰ Таймаут команды (устройство не отвечает)"
        except Exception as e:
            return None, f"❌ Ошибка ADB: {e}"

    def shell(self, args: List[str], timeout: int = 5) -> Tuple[Optional[str], Optional[str]]:
        """Выполнить adb shell <args>"""
        return self.run(["shell"] + args, timeout)

    def get_devices(self) -> List[str]:
        """Получить список подключённых устройств"""
        output, error = self.run(["devices"])
        if error or not output:
            return []

        devices = []
        for line in output.splitlines()[1:]:  # Пропускаем заголовок "List of devices..."
            if "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices

    def reboot(self) -> Tuple[bool, Optional[str]]:
        _, err = self.run(["reboot"])
        return err is None, err

    def shutdown(self) -> Tuple[bool, Optional[str]]:
        _, err = self.run(["shell", "reboot", "-p"])
        return err is None, err


class DeviceInfoParser:
    """
    Парсинг информации об устройстве.
    Все команды — через списки, парсинг — через регулярки (не хрупкий split).
    """

    ANDROID_VERSIONS = {
        35: "Android 15", 34: "Android 14", 33: "Android 13",
        32: "Android 12L", 31: "Android 12", 30: "Android 11",
        29: "Android 10", 28: "Android 9", 27: "Android 8.1",
        26: "Android 8.0", 25: "Android 7.1", 24: "Android 7.0",
        23: "Android 6.0", 22: "Android 5.1", 21: "Android 5.0"
    }

    BATTERY_STATUS = {"2": "Заряжается", "3": "Разряжается", "5": "Полный"}
    BATTERY_HEALTH = {"2": "Хорошее", "3": "Перегрев", "4": "Мертвый", "5": "Перенапряжение", "6": "Ошибка"}

    def __init__(self, adb: ADBExecutor):
        self.adb = adb

    def get_android_version(self) -> str:
        output, _ = self.adb.shell(["getprop", "ro.build.version.sdk"])
        if output and output.strip().isdigit():
            sdk = int(output.strip())
            return self.ANDROID_VERSIONS.get(sdk, f"Android (SDK {sdk})")

        output, _ = self.adb.shell(["getprop", "ro.build.version.release"])
        if output:
            match = re.search(r'^(\d+)', output.strip())
            if match:
                return f"Android {match.group(1)}"
            return f"Android {output.strip()}"
        return "Android Unknown"

    def get_phone_info(self) -> str:
        brand, _ = self.adb.shell(["getprop", "ro.product.brand"])
        model, _ = self.adb.shell(["getprop", "ro.product.model"])
        market_name, _ = self.adb.shell(["getprop", "ro.product.marketname"])

        brand = (brand or "").strip()
        model = (model or "").strip()
        market_name = (market_name or "").strip()

        if market_name and market_name != "Unknown":
            return market_name
        elif brand and model:
            return f"{brand} {model}"
        return "Unknown Device"

    def get_bootloader_status(self) -> str:
        brand, _ = self.adb.shell(["getprop", "ro.product.brand"])
        manufacturer, _ = self.adb.shell(["getprop", "ro.product.manufacturer"])

        brand = (brand or "").lower().strip()
        manufacturer = (manufacturer or "").lower().strip()

        xiaomi_brands = ["xiaomi", "redmi", "poco", "black shark", "blackshark"]
        is_xiaomi = any(b in xiaomi_brands for b in [brand, manufacturer])

        if not is_xiaomi:
            return "🔓 Загрузчик: Не Xiaomi устройство"

        status, _ = self.adb.shell(["getprop", "ro.boot.flash.locked"])
        if status:
            status = status.strip()
            if status == "0":
                return "🔓 Загрузчик: РАЗБЛОКИРОВАН"
            elif status == "1":
                return "🔒 Загрузчик: ЗАБЛОКИРОВАН"
            else:
                return f"🔐 Загрузчик: Неизвестно ({status})"

        verified, _ = self.adb.shell(["getprop", "ro.boot.verifiedbootstate"])
        if verified:
            verified = verified.strip()
            if verified == "orange":
                return "🔓 Загрузчик: РАЗБЛОКИРОВАН (Orange State)"
            elif verified == "green":
                return "🔒 Загрузчик: ЗАБЛОКИРОВАН (Green State)"

        return "🔐 Загрузчик: Не удалось определить"

    def get_cpu_usage(self) -> str:
        output, _ = self.adb.shell(["cat", "/proc/stat"])
        if not output:
            return "🟡 CPU: N/A"

        # Ищем строку "cpu  user nice system idle iowait irq softirq"
        match = re.search(
            r'^cpu\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
            output, re.MULTILINE
        )
        if not match:
            return "🟡 CPU: N/A"

        values = [int(x) for x in match.groups()]
        total_time = sum(values)
        idle_time = values[3]

        if hasattr(self, '_prev_total') and hasattr(self, '_prev_idle'):
            total_diff = total_time - self._prev_total
            idle_diff = idle_time - self._prev_idle
            if total_diff > 0:
                usage = 100 * (total_diff - idle_diff) / total_diff
                icon = "🔴" if usage > 80 else "🟡" if usage > 40 else "🟢"
                return f"{icon} CPU: {usage:.1f}%"

        self._prev_total = total_time
        self._prev_idle = idle_time
        return "🟢 CPU: 0%"

    def get_ram_info(self) -> str:
        output, _ = self.adb.shell(["free", "-m"])
        if not output:
            return "💾 RAM: Ошибка чтения"

        match = re.search(r'Mem:\s+(\d+)\s+(\d+)\s+(\d+)', output)
        if match:
            total, used, free = match.groups()
            percent = (int(used) / int(total)) * 100 if int(total) > 0 else 0
            return f"💾 RAM: {used}/{total}MB ({percent:.1f}%)"
        return "💾 RAM: Ошибка чтения"

    def get_storage_info(self) -> str:
        output, _ = self.adb.shell(["df", "/data"])
        if not output:
            return "💾 Память: Ошибка чтения"

        lines = output.strip().split('\n')
        for line in lines:
            if '/data' in line or (len(lines) == 2 and 'Filesystem' not in line):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        total_kb = int(parts[1])
                        used_kb = int(parts[2])
                        free_kb = int(parts[3])
                        total_gb = total_kb / 1024 / 1024
                        used_gb = used_kb / 1024 / 1024
                        free_gb = free_kb / 1024 / 1024
                        return f"💾 Память: {used_gb:.1f}/{total_gb:.1f}GB свободно {free_gb:.1f}GB"
                    except ValueError:
                        continue
        return "💾 Память: Ошибка чтения"

    def get_battery_info(self) -> str:
        output, _ = self.adb.shell(["dumpsys", "battery"])
        if not output:
            return "🔋 Battery: Ошибка чтения"

        level = "N/A"
        status = "N/A"
        temp = "N/A"

        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('level:'):
                val = line.split(':', 1)[1].strip()
                if val.isdigit():
                    level = f"{val}%"
            elif line.startswith('status:'):
                code = line.split(':', 1)[1].strip()
                status = self.BATTERY_STATUS.get(code, code)
            elif line.startswith('temperature:'):
                val = line.split(':', 1)[1].strip()
                if val.isdigit():
                    temp = f"{int(val) / 10:.1f}°C"

        return f"🔋 Батарея: {level} | {status} | {temp}"

    def get_display_info(self) -> str:
        output, _ = self.adb.shell(["wm", "size"])
        if not output or "Physical size" not in output:
            return "📱 Дисплей: Ошибка чтения"

        match = re.search(r'Physical size:\s*(\d+x\d+)', output)
        resolution = match.group(1) if match else "Unknown"

        # Пробуем получить частоту обновления
        for setting in [
            ["settings", "get", "system", "peak_refresh_rate"],
            ["settings", "get", "system", "screen_refresh_rate"]
        ]:
            rate_output, _ = self.adb.shell(setting)
            if rate_output and rate_output.strip() not in ("null", ""):
                try:
                    rate = float(rate_output.strip())
                    if rate > 1:
                        return f"📱 Дисплей: {resolution} | {rate:.0f}Hz"
                except ValueError:
                    pass

        return f"📱 Дисплей: {resolution} | 60Hz"

    def get_all_stats(self) -> DeviceStats:
        """Получить всю статистику одним вызовом с проверкой подключения"""
        devices = self.adb.get_devices()
        if not devices:
            return DeviceStats(
                phone="📱 Ожидание устройства...",
                version="❌ Подключите устройство",
                bootloader="",
                cpu="",
                ram="",
                storage="",
                battery="",
                display=""
            )

        return DeviceStats(
            phone=self.get_phone_info(),
            version=f"📱 {self.get_android_version()}",
            bootloader=self.get_bootloader_status(),
            cpu=self.get_cpu_usage(),
            ram=self.get_ram_info(),
            storage=self.get_storage_info(),
            battery=self.get_battery_info(),
            display=self.get_display_info()
        )


class BenchmarkRunner:
    """
    Бенчмарк с корректной возможностью остановки.
    Проверяет флаг self.running на каждой итерации — можно прервать в любой момент.
    """

    def __init__(self):
        self.running = False
        self.results = {}
        self._thread: Optional[threading.Thread] = None

    def start(self, on_done_callback):
        if self.running:
            return

        self.running = True
        self.results = {}

        def run():
            # CPU test
            start = time.time()
            for i in range(3_000_000):
                _ = i * i * 3.14159
                if not self.running:
                    return
            self.results['cpu'] = time.time() - start

            # Memory test
            start = time.time()
            test_list = []
            for i in range(100_000):
                test_list.append(i * 2)
                if not self.running:
                    return
            self.results['memory'] = time.time() - start

            # I/O test
            start = time.time()
            temp_data = "x" * 100_000
            for i in range(1_000):
                _ = temp_data.find("test")
                if not self.running:
                    return
            self.results['io'] = time.time() - start

            # Score
            cpu_t = self.results.get('cpu', 1)
            mem_t = self.results.get('memory', 1)
            io_t = self.results.get('io', 1)
            self.results['score'] = (1 / cpu_t * 1000) + (1 / mem_t * 1000) + (1 / io_t * 1000)
            self.running = False

            if on_done_callback:
                on_done_callback()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    @staticmethod
    def get_rating(score: float) -> str:
        if score > 5000:
            return "🚀 Отличная производительность!"
        elif score > 3000:
            return "👍 Хорошая производительность"
        elif score > 2000:
            return "⚠️ Средняя производительность"
        else:
            return "🐌 Низкая производительность"

    def format_results(self) -> str:
        if not self.results:
            return ""
        cpu = self.results.get('cpu', 0)
        mem = self.results.get('memory', 0)
        io = self.results.get('io', 0)
        score = self.results.get('score', 0)

        return f"""
⚡ РЕЗУЛЬТАТЫ БЕНЧМАРКА:

🎯 Общий счет: {score:.0f} points

📊 Детали:
• 🧮 CPU: {cpu:.3f} сек
• 💾 Память: {mem:.3f} сек
• 📁 I/O: {io:.3f} сек

💡 Оценка:
{self.get_rating(score)}
"""


class MonitorApp:
    """
    Главное приложение.
    Вся логика инкапсулирована в класс — никаких глобальных переменных.
    """

    def __init__(self):
        self.adb = ADBExecutor()
        self.parser = DeviceInfoParser(self.adb)
        self.benchmark = BenchmarkRunner()
        self._running = True

        self.root = tk.Tk()
        self.root.title("📊 Android Diagnostic Board (Secure)")
        self.root.geometry("900x800")
        self.root.configure(bg='#2b2b2b')
        self.root.attributes('-fullscreen', False)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.exit_fullscreen)

        self._setup_styles()
        self._setup_ui()
        self._start_monitoring()

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.configure("Custom.TLabel", background='#2b2b2b', foreground='#ffffff', font=('Arial', 11), padding=6)
        self.style.configure("Title.TLabel", background='#2b2b2b', foreground='#4fc3f7', font=('Arial', 14, 'bold'), padding=10)

    def _setup_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=20, pady=10)

        # === Вкладка 1: Основная информация ===
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="📊 Основная информация")

        self.phone_label = ttk.Label(main_tab, text="🔍 Поиск ADB...", style="Title.TLabel")
        self.phone_label.pack(pady=10)

        ttk.Separator(main_tab, orient='horizontal').pack(fill='x', pady=8)

        # Создаём метки через цикл, чтобы не дублировать код
        labels = ['version', 'bootloader', 'cpu', 'ram', 'storage', 'battery', 'display']
        for name in labels:
            lbl = ttk.Label(main_tab, text="", style="Custom.TLabel")
            lbl.pack(pady=4, anchor='w')
            setattr(self, f"{name}_label", lbl)

        # Кнопки управления
        btn_frame = tk.Frame(main_tab, bg='#2b2b2b')
        btn_frame.pack(fill='x', pady=15)

        tk.Button(btn_frame, text="🔄 Перезагрузить", command=self.reboot,
                  bg='#4fc3f7', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8).pack(side='left', padx=5)
        tk.Button(btn_frame, text="⏻ Выключить", command=self.shutdown,
                  bg='#ff6b6b', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8).pack(side='left', padx=5)

        # === Вкладка 2: Бенчмарк ===
        bench_tab = ttk.Frame(notebook)
        notebook.add(bench_tab, text="⚡ Бенчмарк")

        ttk.Label(bench_tab, text="⚡ Тест производительности", style="Title.TLabel").pack(pady=15)
        ttk.Label(bench_tab, text="Тест измеряет производительность CPU, памяти и операций ввода-вывода", style="Custom.TLabel").pack(pady=10)

        bench_btn_frame = tk.Frame(bench_tab, bg='#2b2b2b')
        bench_btn_frame.pack(pady=15)

        tk.Button(bench_btn_frame, text="▶️ Начать тест", command=self.start_benchmark,
                  bg='#4fc3f7', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8).pack(side='left', padx=5)
        tk.Button(bench_btn_frame, text="⏹️ Остановить", command=self.stop_benchmark,
                  bg='#ff6b6b', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8).pack(side='left', padx=5)

        self.bench_status = ttk.Label(bench_tab, text="⏳ Готов к тестированию", style="Custom.TLabel")
        self.bench_status.pack(pady=10)

        self.bench_result = ttk.Label(bench_tab, text="Здесь появятся результаты теста...", style="Custom.TLabel", justify='left')
        self.bench_result.pack(pady=10, fill='both', expand=True)

        # === Статус бар ===
        adb_status = "🟢 ADB найден" if self.adb.is_available() else "🔴 ADB не найден"
        ttk.Label(self.root, text=f"{adb_status} | F11 - Полный экран | ESC - Выход", style="Custom.TLabel").pack(side='bottom', pady=10)

    def _start_monitoring(self):
        """Фоновый поток опроса устройства (1 раз в секунду)"""
        def monitor_loop():
            while self._running:
                try:
                    stats = self.parser.get_all_stats()
                    # Безопасное обновление UI из главного потока
                    self.root.after(0, self._update_labels, stats)
                except Exception as e:
                    self._log_error(f"Monitor loop error: {e}")
                time.sleep(1)

        threading.Thread(target=monitor_loop, daemon=True).start()

    def _update_labels(self, stats: DeviceStats):
        """Обновление меток в главном потоке"""
        self.phone_label.config(text=stats.phone)
        self.version_label.config(text=stats.version)
        self.bootloader_label.config(text=stats.bootloader)
        self.cpu_label.config(text=stats.cpu)
        self.ram_label.config(text=stats.ram)
        self.storage_label.config(text=stats.storage)
        self.battery_label.config(text=stats.battery)
        self.display_label.config(text=stats.display)

    def _log_error(self, msg: str):
        """Запись ошибки в лог-файл"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            with open(f"error-{timestamp}.txt", 'w', encoding='utf-8') as f:
                f.write(f"ADB Monitor Error - {timestamp}\n{msg}\n")
                f.write(f"Platform: {platform.system()}\nPython: {platform.python_version()}\n")
        except Exception:
            pass

    def toggle_fullscreen(self, event=None):
        self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen'))

    def exit_fullscreen(self, event=None):
        self.root.attributes('-fullscreen', False)

    def reboot(self):
        if messagebox.askyesno("Перезагрузка", "Вы уверены что хотите перезагрузить устройство?"):
            ok, err = self.adb.reboot()
            if not ok:
                messagebox.showerror("Ошибка", f"Не удалось перезагрузить: {err}")
            else:
                messagebox.showinfo("Успех", "Устройство перезагружается...")

    def shutdown(self):
        if messagebox.askyesno("Выключение", "Вы уверены что хотите выключить устройство?"):
            ok, err = self.adb.shutdown()
            if not ok:
                messagebox.showerror("Ошибка", f"Не удалось выключить: {err}")
            else:
                messagebox.showinfo("Успех", "Устройство выключается...")

    def start_benchmark(self):
        self.benchmark.start(self._on_benchmark_done)
        self.bench_status.config(text="🔄 Тест выполняется...")

    def stop_benchmark(self):
        self.benchmark.stop()
        self.bench_status.config(text="⏹️ Тест остановлен")

    def _on_benchmark_done(self):
        """Callback из фонового потока -> планируем обновление UI в главном потоке"""
        self.root.after(0, self._update_benchmark_ui)

    def _update_benchmark_ui(self):
        self.bench_result.config(text=self.benchmark.format_results())
        self.bench_status.config(text="✅ Тест завершен")

    def run(self):
        self.root.eval('tk::PlaceWindow . center')
        self.root.mainloop()
        self._running = False


if __name__ == "__main__":
    app = MonitorApp()
    app.run()
