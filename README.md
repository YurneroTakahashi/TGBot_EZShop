

---

##  Быстрая установка

1. **Создайте виртуальное окружение**
   ```bash
   python -m venv venv
   source venv/bin/activate    # Linux/Mac
   venv\Scripts\activate       # Windows
   ```

2. **Установите зависимости**
   ```bash
   pip install -r requirements.txt
   ```

3. **Настройте бота**
   ```bash
   cp .env.example .env
   ```
   Откройте `.env` и укажите:
   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
   - `ADMIN_IDS` — ваш Telegram ID (узнать у [@userinfobot](https://t.me/userinfobot))

4. **Запустите**
   ```bash
   python bot.py
   ```

5. **Настройте группу заявок**  
   Добавьте бота в группу как администратора и отправьте там команду:
   ```
   /setgroup
   ```

Готово! Бот полностью работоспособен.
