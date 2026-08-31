import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import time
import re
import os
import platform
import datetime

# Глобальные переменные для бенчмарка
benchmark_running = False
benchmark_results = {}

def find_adb():
    """Автоматический поиск adb.exe в системе"""
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
    
    # Проверяем PATH
    for path_dir in os.environ.get('PATH', '').split(os.pathsep):
        adb_path = os.path.join(path_dir, 'adb.exe' if platform.system() == "Windows" else 'adb')
        if os.path.isfile(adb_path):
            return adb_path
    
    # Проверяем возможные пути
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    
    return None

def log_error(error_msg):
    """Запись ошибок в лог файл"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"error-{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"ADB Monitor Error - {timestamp}\n")
            f.write(f"Error: {error_msg}\n")
            f.write(f"Platform: {platform.system()}\n")
            f.write(f"Python: {platform.python_version()}\n")
        return filename
    except Exception as e:
        print(f"Не удалось записать лог: {e}")

def adb_command(cmd, timeout=5):
    """Выполнение ADB команд с обработкой ошибок"""
    try:
        adb_path = find_adb()
        if not adb_path:
            return None, "❌ ADB не найден"
        
        full_cmd = f'"{adb_path}" {cmd}'
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=timeout
        )
        return result.stdout.strip(), None
    except subprocess.TimeoutExpired:
        return None, "⏰ Таймаут команды"
    except Exception as e:
        error_msg = f"❌ Ошибка ADB: {str(e)}"
        log_error(error_msg)
        return None, error_msg

def adb_shell(cmd):
    """Универсальная функция для выполнения ADB shell команд"""
    output, error = adb_command(f'shell "{cmd}"')
    return output if output else error

def get_android_version():
    """Получение человеко-читаемой версии Android"""
    try:
        # Получаем версию SDK
        sdk_version = adb_shell("getprop ro.build.version.sdk")
        if sdk_version and sdk_version.isdigit():
            sdk = int(sdk_version)
            # Маппинг версий SDK на Android версии
            android_versions = {
                35: "Android 15",
                34: "Android 14",
                33: "Android 13", 
                32: "Android 12L",
                31: "Android 12",
                30: "Android 11",
                29: "Android 10",
                28: "Android 9",
                27: "Android 8.1",
                26: "Android 8.0",
                25: "Android 7.1",
                24: "Android 7.0",
                23: "Android 6.0",
                22: "Android 5.1",
                21: "Android 5.0"
            }
            return android_versions.get(sdk, f"Android (SDK {sdk})")
        
        # Если не получилось через SDK, пробуем через версию релиза
        release_version = adb_shell("getprop ro.build.version.release")
        if release_version:
            # Пытаемся извлечь основную версию (14, 15, etc)
            version_match = re.search(r'^(\d+)', release_version)
            if version_match:
                version_num = version_match.group(1)
                return f"Android {version_num}"
            return f"Android {release_version}"
        
        return "Android Unknown"
    except Exception as e:
        return "Android Unknown"

def check_xiaomi_bootloader():
    """Проверка состояния загрузчика для Xiaomi устройств"""
    try:
        # Проверяем, является ли устройство Xiaomi
        brand = adb_shell("getprop ro.product.brand") or ""
        manufacturer = adb_shell("getprop ro.product.manufacturer") or ""
        
        xiaomi_brands = ["xiaomi", "redmi", "poco", "black shark", "blackshark"]
        is_xiaomi = any(brand.lower() in xiaomi_brands for brand in [brand, manufacturer])
        
        if not is_xiaomi:
            return "🔓 Загрузчик: Не Xiaomi устройство"
        
        bootloader_status = adb_shell("getprop ro.boot.flash.locked")
        
        if bootloader_status:
            if bootloader_status == "0":
                return "🔓 Загрузчик: РАЗБЛОКИРОВАН"
            elif bootloader_status == "1":
                return "🔒 Загрузчик: ЗАБЛОКИРОВАН"
            else:
                return f"🔐 Загрузчик: Неизвестно ({bootloader_status})"
        
        verified_boot = adb_shell("getprop ro.boot.verifiedbootstate")
        if verified_boot:
            if verified_boot == "orange":
                return "🔓 Загрузчик: РАЗБЛОКИРОВАН (Orange State)"
            elif verified_boot == "green":
                return "🔒 Загрузчик: ЗАБЛОКИРОВАН (Green State)"
        
        return "🔐 Загрузчик: Не удалось определить"
        
    except Exception as e:
        return f"🔐 Загрузчик: Ошибка проверки"

def reboot_device():
    """Перезагрузка устройства"""
    result = messagebox.askyesno("Перезагрузка", "Вы уверены что хотите перезагрузить устройство?")
    if result:
        output, error = adb_command("reboot")
        if error:
            messagebox.showerror("Ошибка", f"Не удалось перезагрузить: {error}")
        else:
            messagebox.showinfo("Успех", "Устройство перезагружается...")

def shutdown_device():
    """Выключение устройства"""
    result = messagebox.askyesno("Выключение", "Вы уверены что хотите выключить устройство?")
    if result:
        output, error = adb_command("shell reboot -p")
        if error:
            messagebox.showerror("Ошибка", f"Не удалось выключить: {error}")
        else:
            messagebox.showinfo("Успех", "Устройство выключается...")

def get_real_storage():
    """Проверка реальной памяти устройства"""
    try:
        storage_info = adb_shell("df /data | grep /data")
        if storage_info and "Ошибка" not in storage_info:
            parts = storage_info.split()
            if len(parts) >= 5:
                total_kb = int(parts[1])
                used_kb = int(parts[2])
                free_kb = int(parts[3])
                
                total_gb = total_kb / 1024 / 1024
                used_gb = used_kb / 1024 / 1024
                free_gb = free_kb / 1024 / 1024
                
                return f"💾 Память: {used_gb:.1f}/{total_gb:.1f}GB свободно {free_gb:.1f}GB"
        
        return "💾 Память: Ошибка чтения"
    except Exception as e:
        return f"💾 Память: Ошибка - {str(e)}"

def run_benchmark():
    """Запуск бенчмарка производительности"""
    global benchmark_running, benchmark_results
    
    if benchmark_running:
        return
    
    benchmark_running = True
    benchmark_results = {}
    
    def benchmark_thread():
        # Тест CPU - математические операции
        start_time = time.time()
        for i in range(3000000):
            _ = i * i * 3.14159
        cpu_time = time.time() - start_time
        benchmark_results['cpu'] = cpu_time
        
        # Тест памяти - операции с списками
        start_time = time.time()
        test_list = []
        for i in range(100000):
            test_list.append(i * 2)
        memory_time = time.time() - start_time
        benchmark_results['memory'] = memory_time
        
        # Тест ввода-вывода
        start_time = time.time()
        temp_data = "x" * 100000
        for i in range(1000):
            _ = temp_data.find("test")
        io_time = time.time() - start_time
        benchmark_results['io'] = io_time
        
        # Расчет общего счета
        total_score = (1 / cpu_time * 1000) + (1 / memory_time * 1000) + (1 / io_time * 1000)
        benchmark_results['score'] = total_score
        
        benchmark_running = False
        
        # Обновляем интерфейс в основном потоке
        root.after(0, update_benchmark_results)
    
    threading.Thread(target=benchmark_thread, daemon=True).start()
    benchmark_status_label.config(text="🔄 Тест выполняется...")

def stop_benchmark():
    """Остановка бенчмарка"""
    global benchmark_running
    benchmark_running = False
    benchmark_status_label.config(text="⏹️ Тест остановлен")

def update_benchmark_results():
    """Обновление результатов бенчмарка"""
    if benchmark_results:
        cpu_time = benchmark_results.get('cpu', 0)
        memory_time = benchmark_results.get('memory', 0)
        io_time = benchmark_results.get('io', 0)
        score = benchmark_results.get('score', 0)
        
        result_text = f"""
⚡ РЕЗУЛЬТАТЫ БЕНЧМАРКА:

🎯 Общий счет: {score:.0f} points

📊 Детали:
• 🧮 CPU: {cpu_time:.3f} сек
• 💾 Память: {memory_time:.3f} сек  
• 📁 I/O: {io_time:.3f} сек

💡 Оценка:
{get_performance_rating(score)}
"""
        benchmark_result_label.config(text=result_text)
        benchmark_status_label.config(text="✅ Тест завершен")

def get_performance_rating(score):
    """Оценка производительности по результатам"""
    if score > 5000:
        return "🚀 Отличная производительность!"
    elif score > 3000:
        return "👍 Хорошая производительность"
    elif score > 2000:
        return "⚠️ Средняя производительность"
    else:
        return "🐌 Низкая производительность"

def get_display_refresh_rate():
    """Получение текущей частоты обновления дисплея"""
    try:
        # Простой способ - через настройки
        current_rate = adb_shell("settings get system peak_refresh_rate")
        if current_rate and current_rate != "null" and "Ошибка" not in current_rate:
            try:
                rate = float(current_rate)
                if rate > 1:
                    return f"{rate:.0f}Hz"
            except:
                pass
        
        # Альтернативный способ для MIUI
        miui_rate = adb_shell("settings get system screen_refresh_rate") 
        if miui_rate and miui_rate != "null" and "Ошибка" not in miui_rate:
            try:
                rate = float(miui_rate)
                if rate > 1:
                    return f"{rate:.0f}Hz"
            except:
                pass
        
        return "60Hz"  # Значение по умолчанию
        
    except Exception as e:
        return "60Hz"

def get_stats_via_adb():
    try:
        # Проверка подключения
        adb_check, error = adb_command("devices")
        if error or not adb_check or "device" not in adb_check:
            return "📱 Ожидание устройства...", "❌ Подключите устройство", "", "", "", "", "", ""

        # Получаем человеко-читаемую версию Android
        android_version = get_android_version()
        
        # Информация о телефоне
        brand = adb_shell("getprop ro.product.brand") or ""
        model = adb_shell("getprop ro.product.model") or ""
        market_name = adb_shell("getprop ro.product.marketname") or ""
        
        if market_name and market_name != "Unknown":
            phone_info = f"{market_name}"
        elif brand and model:
            phone_info = f"{brand} {model}"
        else:
            phone_info = "Unknown Device"

        # Версия Android отдельно
        version_info = f"📱 {android_version}"

        # Проверка загрузчика для Xiaomi
        bootloader_info = check_xiaomi_bootloader()

        # Загрузка CPU
        cpu = "0"
        stat_output = adb_shell("cat /proc/stat | grep '^cpu '")
        if stat_output and "Ошибка" not in stat_output:
            parts = stat_output.split()
            if len(parts) >= 8:
                total_time = sum(int(x) for x in parts[1:8])
                idle_time = int(parts[4])
                if hasattr(get_stats_via_adb, 'prev_total') and hasattr(get_stats_via_adb, 'prev_idle'):
                    total_diff = total_time - get_stats_via_adb.prev_total
                    idle_diff = idle_time - get_stats_via_adb.prev_idle
                    if total_diff > 0:
                        cpu_usage = 100 * (total_diff - idle_diff) / total_diff
                        cpu = f"{cpu_usage:.1f}"
                
                get_stats_via_adb.prev_total = total_time
                get_stats_via_adb.prev_idle = idle_time
        
        # Цвет индикатора CPU
        cpu_color = "🟢"
        if float(cpu) > 80:
            cpu_color = "🔴"
        elif float(cpu) > 40:
            cpu_color = "🟡"
            
        cpu_info = f"{cpu_color} CPU: {cpu}%"

        # RAM информация
        ram_output = adb_shell("free -m")
        ram_info = "💾 RAM: Ошибка чтения"
        
        if ram_output and "Ошибка" not in ram_output:
            for line in ram_output.split('\n'):
                if 'Mem:' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        ram_used = parts[2]
                        ram_total = parts[1]
                        ram_percent = f"{(int(ram_used)/int(ram_total))*100:.1f}%" if ram_total != "0" else "0%"
                        ram_info = f"💾 RAM: {ram_used}/{ram_total}MB ({ram_percent})"
                    break

        # Реальная память устройства
        storage_info = get_real_storage()

        # Информация о батарее
        battery_output = adb_shell("dumpsys battery")
        battery_info = "🔋 Battery: Ошибка чтения"
        
        if battery_output and "Ошибка" not in battery_output:
            battery_level = "N/A"
            battery_technology = "N/A"
            battery_status = "N/A"
            battery_health = "N/A"
            battery_temp = "N/A"
            
            for line in battery_output.split('\n'):
                if 'level:' in line:
                    battery_value = line.split(':')[1].strip()
                    if battery_value.isdigit():
                        battery_level = f"{battery_value}%"
                elif 'technology:' in line:
                    battery_technology = line.split(':')[1].strip()
                elif 'status:' in line:
                    status_code = line.split(':')[1].strip()
                    status_map = {"2": "Заряжается", "3": "Разряжается", "5": "Полный"}
                    battery_status = status_map.get(status_code, status_code)
                elif 'health:' in line:
                    health_code = line.split(':')[1].strip()
                    health_map = {"2": "Хорошее", "3": "Перегрев", "4": "Мертвый", "5": "Перенапряжение", "6": "Ошибка"}
                    battery_health = health_map.get(health_code, health_code)
                elif 'temperature:' in line:
                    temp_value = line.split(':')[1].strip()
                    if temp_value.isdigit():
                        temp_c = int(temp_value) / 10.0
                        battery_temp = f"{temp_c:.1f}°C"
            
            battery_info = f"🔋 Батарея: {battery_level} | {battery_status} | {battery_temp}"

        # Информация о дисплее
        display_info = "📱 Дисплей: Ошибка чтения"
        size_output = adb_shell("wm size")
        
        if size_output and "Ошибка" not in size_output and "Physical size" in size_output:
            resolution = size_output.split(":")[1].strip()
            refresh_rate = get_display_refresh_rate()
            
            display_info = f"📱 Дисплей: {resolution} | {refresh_rate}"

        return phone_info, version_info, bootloader_info, cpu_info, ram_info, storage_info, battery_info, display_info

    except Exception as e:
        error_msg = f"❌ Системная ошибка: {str(e)}"
        log_error(error_msg)
        return "📱 Ошибка", error_msg, "", "", "", "", "", ""

# Инициализация переменных
get_stats_via_adb.prev_total = 0
get_stats_via_adb.prev_idle = 0

def update_stats():
    while True:
        try:
            phone, version, bootloader, cpu, ram, storage, battery, display = get_stats_via_adb()
            phone_label.config(text=phone)
            version_label.config(text=version)
            bootloader_label.config(text=bootloader)
            cpu_label.config(text=cpu)
            ram_label.config(text=ram)
            storage_label.config(text=storage)
            battery_label.config(text=battery)
            display_label.config(text=display)
            
        except Exception as e:
            log_error(f"Update error: {str(e)}")
        time.sleep(0.5)

def toggle_fullscreen(event=None):
    root.attributes('-fullscreen', not root.attributes('-fullscreen'))

def exit_fullscreen(event=None):
    root.attributes('-fullscreen', False)

# Создание GUI
root = tk.Tk()
root.title("📊 Android Diagnostic Board")
root.geometry("900x800")
root.configure(bg='#2b2b2b')

# Настройки полноэкранного режима
root.attributes('-fullscreen', False)
root.bind('<F11>', toggle_fullscreen)
root.bind('<Escape>', exit_fullscreen)

# Notebook для вкладок
notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True, padx=20, pady=10)

# Стиль для меток
style = ttk.Style()
style.configure("Custom.TLabel", 
                background='#2b2b2b',
                foreground='#ffffff',
                font=('Arial', 11),
                padding=6)

style.configure("Title.TLabel",
                background='#2b2b2b',
                foreground='#4fc3f7',
                font=('Arial', 14, 'bold'),
                padding=10)

# Вкладка 1: Основная информация
main_tab = ttk.Frame(notebook, style="Custom.TLabel")
notebook.add(main_tab, text="📊 Основная информация")

phone_label = ttk.Label(main_tab, text="🔍 Поиск ADB...", style="Title.TLabel")
phone_label.pack(pady=10)

separator = ttk.Separator(main_tab, orient='horizontal')
separator.pack(fill='x', pady=8)

version_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
version_label.pack(pady=4, anchor='w')

bootloader_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
bootloader_label.pack(pady=4, anchor='w')

cpu_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
cpu_label.pack(pady=4, anchor='w')

ram_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
ram_label.pack(pady=4, anchor='w')

storage_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
storage_label.pack(pady=4, anchor='w')

battery_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
battery_label.pack(pady=4, anchor='w')

display_label = ttk.Label(main_tab, text="", style="Custom.TLabel")
display_label.pack(pady=4, anchor='w')

# Кнопки управления в основной вкладке
main_button_frame = tk.Frame(main_tab, bg='#2b2b2b')
main_button_frame.pack(fill='x', pady=15)

reboot_btn = tk.Button(main_button_frame, text="🔄 Перезагрузить", command=reboot_device,
                      bg='#4fc3f7', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8)
reboot_btn.pack(side='left', padx=5)

shutdown_btn = tk.Button(main_button_frame, text="⏻ Выключить", command=shutdown_device,
                        bg='#ff6b6b', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8)
shutdown_btn.pack(side='left', padx=5)

# Вкладка 2: Бенчмарк
benchmark_tab = ttk.Frame(notebook, style="Custom.TLabel")
notebook.add(benchmark_tab, text="⚡ Бенчмарк")

benchmark_title = ttk.Label(benchmark_tab, text="⚡ Тест производительности", style="Title.TLabel")
benchmark_title.pack(pady=15)

benchmark_info = ttk.Label(benchmark_tab, text="Тест измеряет производительность CPU, памяти и операций ввода-вывода", style="Custom.TLabel")
benchmark_info.pack(pady=10)

# Кнопки бенчмарка
benchmark_button_frame = tk.Frame(benchmark_tab, bg='#2b2b2b')
benchmark_button_frame.pack(pady=15)

start_benchmark_btn = tk.Button(benchmark_button_frame, text="▶️ Начать тест", command=run_benchmark,
                              bg='#4fc3f7', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8)
start_benchmark_btn.pack(side='left', padx=5)

stop_benchmark_btn = tk.Button(benchmark_button_frame, text="⏹️ Остановить", command=stop_benchmark,
                             bg='#ff6b6b', fg='black', font=('Arial', 10, 'bold'), padx=15, pady=8)
stop_benchmark_btn.pack(side='left', padx=5)

# Статус бенчмарка
benchmark_status_label = ttk.Label(benchmark_tab, text="⏳ Готов к тестированию", style="Custom.TLabel")
benchmark_status_label.pack(pady=10)

# Результаты бенчмарка
benchmark_result_label = ttk.Label(benchmark_tab, text="Здесь появятся результаты теста...", style="Custom.TLabel", justify='left')
benchmark_result_label.pack(pady=10, fill='both', expand=True)

# Статус бар
status_bar = ttk.Label(root, text="🟢 ADB Diagnostic Board | F11 - Полный экран | ESC - Выход", style="Custom.TLabel")
status_bar.pack(side='bottom', pady=10)

# Запуск
thread = threading.Thread(target=update_stats, daemon=True)
thread.start()

root.eval('tk::PlaceWindow . center')
root.mainloop()