import constants
import telebot 
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yfinance as yf
import database
import logging
from logger_config import setup_logger
import os

logger = setup_logger(os.path.basename(__file__))

class IgnorePeerReset(logging.Filter):
    def filter(self, r):
        m = r.getMessage()
        return ("Connection reset by peer" not in m and "Read timed out" not in m)

logging.getLogger("TeleBot").addFilter(IgnorePeerReset())
logging.getLogger("urllib3.connectionpool").addFilter(IgnorePeerReset())

# Telegram token stored in constants.py
TELEGRAM_TOKEN = constants.TELEGRAM_TOKEN

# Create an instance of Telebot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Create alerts database and table if they don't exist
connection = database.connect()
database.create_table(connection)

# Define a command handler for /start or /help
@bot.message_handler(commands=["start", "help"])
def start_menu(message):
    """Sends a start menu with options to add, delete, or show stock alerts."""
    markup = InlineKeyboardMarkup()
    markup.row_width = 3
    markup.add(
        InlineKeyboardButton("Add alert", callback_data="cb_add"),
        InlineKeyboardButton("Delete alert", callback_data="cb_delete"),
        InlineKeyboardButton("Show all alerts", callback_data="cb_show"),
    )
    bot.send_message(message.chat.id, "Select what you want to do:", reply_markup=markup)

# Define a callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handles callback queries from the inline keyboard options."""
    if call.data == "cb_add":
        logger.info(f"chat_id: {call.message.chat.id}: Add Alert button clicked")
        add_alert(call)
    elif call.data == "cb_delete":
        logger.info(f"chat_id: {call.message.chat.id}: Delete Alert button clicked")
        delete_alert(call)
    elif call.data == "cb_show":
        logger.info(f"chat_id: {call.message.chat.id}: Show Alerts button clicked")
        show_all_alerts(call)

def add_alert(call):
    """Prompts the user to input the stock ticker symbol for the alert."""
    bot.send_message(call.message.chat.id, "Type the ticker symbol which you would like to add.")
    logger.info(f"chat_id: {call.message.chat.id}: Sent prompt for ticker symbol. Waiting for response.")
    bot.register_next_step_handler(call.message, validate_ticker_and_price_data)

def delete_alert(call):
    """Prompts the user to delete an existing stock alert."""
    connection = database.connect()
    all_alerts = database.get_all_alerts(connection, call.message.chat.id)
    if all_alerts:
        bot.send_message(call.message.chat.id, "Type the alert ID which you would like to delete.")
        show_all_alerts(call)
        logger.info(f"chat_id: {call.message.chat.id}: Sent prompt for ticker symbol. Waiting for response.")
        bot.register_next_step_handler(call.message, validate_row_number)
    else:
        bot.send_message(call.message.chat.id, "No alerts added yet.")
        logger.info(f"chat_id: {call.message.chat.id}: Alerts list is empty. Error message sent.")

def validate_row_number(message):
    """Validates the user input for alert deletion."""
    logger.info(f"chat_id: {message.chat.id}: Received response: {message.text}")
    validated_row_number = int(message.text) if message.text.isdigit() else None 
    if validated_row_number:
        logger.info(f"chat_id: {message.chat.id}: Response {validated_row_number} is a valid row number.")
        connection = database.connect()
        database.delete_alert_by_row_number(connection, message.chat.id, validated_row_number)
        bot.send_message(message.chat.id, "Alert deleted.")
    else:
        bot.send_message(message.chat.id, "That's not a valid alert ID. Please provide only the number.")

def show_all_alerts(call):
    """Fetches and displays all alerts for the user with optimized formatting."""
    connection = database.connect()
    all_alerts = database.get_all_alerts(connection, call.message.chat.id)
    
    if all_alerts:
        # Optimize alert formatting for brevity
        formatted_alerts = [
            f"<b>Alert {row[5]}:</b> {row[2]} @ {row[4]} (Alert: {row[3]})"
            for row in all_alerts
        ]
        formatted_alerts_text = "\n".join(formatted_alerts)
        
        # Send the formatted message
        bot.send_message(call.message.chat.id, formatted_alerts_text, parse_mode="html")
        logger.info(f"chat_id: {call.message.chat.id}: Alert list sent.")
    else:
        bot.send_message(call.message.chat.id, "No alerts have been added yet")
        logger.info(f"chat_id: {call.message.chat.id}: Alerts list is empty. Error message sent.")

def validate_ticker_and_price_data(message):
    """Validates the ticker symbol entered by the user and fetches stock data."""
    logger.info(f"chat_id: {message.chat.id}: Received response: {message.text}")
    validated_ticker = validate_ticker(message)
    if validated_ticker:
        # Fetch price data from Yahoo Finance
        bot.send_message(message.chat.id, "Attempting download of price data. Please wait.")
        logger.info(f"chat_id: {message.chat.id}: Download price data for {validated_ticker}")
        price_data = yf.download(validated_ticker, period="1y", auto_adjust=True, progress=False)

        # Check if price data is available
        if price_data.empty:
            send_error_message(message, category="ticker symbol", reason="a lack of price data")
            logger.info(f"chat_id: {message.chat.id}: Price data for {validated_ticker} is empty. Error message sent.")
        else:
            validated_price_data = price_data
            last_close = validated_price_data[("Close", validated_ticker)].iloc[-1]
            last_date = validated_price_data.index[-1].date()
            alert_prompt = f"The last close price for {validated_ticker} is {last_close:.2f} on {last_date}.\n\nAdd an alert level for {validated_ticker}. For example:\n130.02\nMA100 (100 daily moving average)\n10%\n-5.5%"
            bot.send_message(message.chat.id, alert_prompt)
            logger.info(f"chat_id: {message.chat.id}: Price data for {validated_ticker} is valid. Prompt for alert level sent. Waiting for reply.")
            bot.register_next_step_handler(message, validate_alert_level, validated_ticker, validated_price_data)

def validate_ticker(message):
    """Validates the stock ticker entered by the user."""
    logger.info(f"chat_id: {message.chat.id}: Validating ticker symbol {message.text}")
    if any(s in message.text for s in ", "):
        send_error_message(message, category="ticker symbol", reason="an illegal character")
        logger.info(f"chat_id: {message.chat.id}: Error message sent due to illegal character in ticker symbol: {message.text}")
    else:
        logger.info(f"chat_id: {message.chat.id}: Ticker symbol {message.text} is valid.")
        validated_ticker = message.text.upper()
        return validated_ticker

def validate_alert_level(message, validated_ticker_symbol, validated_price_data):
    """Validates the alert level entered by the user and adds the alert to the database."""
    logger.info(f"chat_id: {message.chat.id}: Received response: {message.text}. Validating {message.text} for ticker {validated_ticker_symbol}.")
    
    # Get the last close price
    last_close = round(validated_price_data[("Close", validated_ticker_symbol)].iloc[-1], 2)
    
    # Check if alert level is valid (percentage, price, or moving average)
    if message.text.startswith("MA") and message.text.replace("MA", "", 1).isdigit():
        # Extract the MA period (e.g., 1400 from MA1400)
        ma_period = int(message.text.replace("MA", ""))
        
        # Check if the available data points are enough for the MA period
        available_data_points = len(validated_price_data.dropna())
        if ma_period > available_data_points:
            # If the MA period exceeds available data points, send an error message
            send_error_message(message, category="MA period", reason=f"not enough data to calculate MA{ma_period}. Only {available_data_points} days of data are available.")
            logger.info(f"chat_id: {message.chat.id}: Not enough data to calculate MA{ma_period}. Only {available_data_points} data points available. Error message sent.")
            return
        
        # If enough data is available, proceed with adding the alert
        validated_alert_level = message.text
    elif message.text.replace("%", "", 1).replace(".", "", 1).replace("-", "", 1).isdigit() and message.text.endswith("%") and (message.text.startswith("-") or message.text[0].isdigit()):
        validated_alert_level = round((1 + float(message.text.replace("%", "", 1)) / 100) * last_close, 2)
    elif message.text.replace(".", "", 1).isdigit():
        validated_alert_level = round(float(message.text), 2)
    else:
        # Send error if alert level is invalid
        send_error_message(message, category="alert level", reason="a wrong price input")
        logger.info(f"chat_id: {message.chat.id}: Alert level {message.text} is not valid. Error message sent.")
        return
    
    logger.info(f"chat_id: {message.chat.id}: Alert level {message.text} is valid. Adding to database.")
    add_alert_to_database(message, validated_ticker_symbol, validated_alert_level, last_close)

def add_alert_to_database(message, validated_ticker_symbol, validated_alert_level, last_close):
    """Adds the validated alert to the database."""
    connection = database.connect()
    database.add_alert(connection, message.chat.id, validated_ticker_symbol, validated_alert_level, last_close)
    bot.send_message(message.chat.id, f"Successfully added alert for {validated_ticker_symbol} at {validated_alert_level}!")

def send_error_message(message, category, reason):
    """Sends an error message to the user."""
    bot.send_message(message.chat.id, f"Invalid {category} due to {reason}! Please enter a valid one.")

# Start polling for bot updates
bot.infinity_polling()
