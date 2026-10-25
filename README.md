# Reshapyx

Небольшой сервис на FastAPI и Pillow для обработки изображений: получение
характеристик, изменение размера с сохранением пропорций и конвертация
между PNG, JPEG и WebP.

## Запуск на macOS / Linux

Требуется Python 3.12.

```bash
git clone https://github.com/dangannn/reshapyx.git
cd reshapyx
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

Откройте http://127.0.0.1:8000/docs, выберите операцию, нажмите **Try it out**,
загрузите изображение и выполните запрос.

Для запуска во время разработки с автоматическим перезапуском:

```bash
python -m uvicorn app_final:app --reload
```
