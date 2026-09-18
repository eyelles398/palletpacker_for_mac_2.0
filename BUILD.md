# Сборка PalletPacker

## Windows: .exe + установщик

### 1. Окружение

    cd D:\proekt\for_git
    python -m venv venv
    venv\Scripts\activate
    pip install PySide6 pyqtgraph PyOpenGL numpy openpyxl pillow pywin32 pyinstaller

### 2. Иконка

    python make_icon.py

### 3. Очистка

    rmdir /s /q build
    rmdir /s /q dist

### 4. Сборка exe

    pyinstaller --noconfirm --windowed --name PalletPacker ^
      --icon=icon.ico ^
      --hidden-import=pyqtgraph.opengl ^
      --hidden-import=OpenGL.platform.win32 ^
      --hidden-import=PySide6.QtPrintSupport ^
      --hidden-import=openpyxl ^
      --hidden-import=win32com.client ^
      --collect-submodules=openpyxl ^
      --collect-data=pyqtgraph ^
      main.py

### 5. Данные рядом с exe

    copy devices.json dist\PalletPacker\
    copy icon.ico    dist\PalletPacker\

### 6. Проверка

    dist\PalletPacker\PalletPacker.exe

### 7. Установщик

Открой Inno Setup Compiler -> File -> Open -> installer.iss -> F9.

Результат: installer_output\PalletPacker_Setup_1.5.1.exe.

---

## macOS: .app

Через GitHub Actions (рекомендуется).

Workflow: .github/workflows/build-mac.yml

Запуск: push в ветку main.

Скачивание: GitHub -> Actions -> последний успешный билд ->
Artifacts -> PalletPacker-mac.zip.

Локальная сборка (только на Mac):

    python -m venv venv
    source venv/bin/activate
    pip install PySide6 pyqtgraph PyOpenGL numpy openpyxl pillow py2app
    python make_icns.py
    python setup.py py2app

Результат: dist/PalletPacker.app.

---

## Обновление версии

1. installer.iss: #define AppVersion "X.Y"
2. setup.py: CFBundleVersion и CFBundleShortVersionString
3. Коммит, push -> GitHub Actions пересоберёт macOS-версию