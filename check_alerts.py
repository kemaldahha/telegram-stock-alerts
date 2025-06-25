import constants
import database
import telebot
import yfinance as yf
from logger_config import setup_logger
import os

def main():
    """Main function that fetches and checks stock alerts for all users,
    and triggers notifications if conditions are met."""
    
    # Set up logging for this script
    logger = setup_logger(os.path.basename(__file__))
    logger.info("Start")

    # Telegram token stored in constants.py
    TELEGRAM_TOKEN = constants.TELEGRAM_TOKEN

    # Create an instance of the Telebot class with the provided token
    bot = telebot.TeleBot(TELEGRAM_TOKEN)

    # Get all chat_ids with active alerts
    connection = database.connect()
    all_chat_ids = database.get_all_chat_ids(connection)

    # Get all stock alerts
    connection = database.connect()
    all_alerts = database.get_all_alerts(connection)

    # Extract all unique tickers from the alerts
    all_tickers = set([alert[2] for alert in all_alerts])

    # Raise an error if there are fewer than 2 alerts, as the script needs more data
    error_message = "Need at least 2 alerts for this script to work"
    if len(all_tickers) < 2:
        logger.error(error_message)
        raise ValueError(error_message)
    
    logger.info(f"Downloading price data for all alerts")

    # Download price data for all tickers over the past year
    price_data = yf.download(all_tickers, period="1y", auto_adjust=True, progress=False)

    # Check the last price against the alert level for each alert
    for alert in all_alerts:
        alert_id, chat_id, ticker, alert_level, last_close, _ = alert

        # Get the latest close price for the current ticker
        current_close = round(price_data[("Close", ticker)].loc[price_data[("Close", ticker)].last_valid_index()], 2)

        # Handle alerts based on Moving Average (MA)
        if "MA" in alert_level:
            # Calculate the moving average for the given period (e.g., MA100 for 100-day MA)
            alert_level_MA = price_data[("Close", ticker)].dropna().rolling(window=int(alert_level.split("MA")[1])).mean().iloc[-1]
            logger.info(f"chat_id: {chat_id}: Checking alert_id {alert_id} at alert level {alert_level} ({alert_level_MA:.2f}) for {ticker} at last close {last_close} and current close {current_close}")
            
            # Trigger alert if the current price crosses the MA level
            if (last_close < alert_level_MA and current_close > alert_level_MA) or (last_close > alert_level_MA and current_close < alert_level_MA):
                bot.send_message(chat_id, f"Alert triggered for {ticker}! Current close price {current_close} has crossed alert level {alert_level} ({alert_level_MA:.2f}).")
                connection = database.connect()
                database.delete_alert(connection, alert_id)
                logger.info(f"chat_id: {chat_id}: Alert message sent for {ticker} at alert level {alert_level} ({alert_level_MA:.2f}). Alert deleted.")
            else:
                # Update the last close price if no alert was triggered
                connection = database.connect()
                database.update_close_price(connection, alert_id, current_close)
                logger.info(f"chat_id: {chat_id}: Alert not triggered for {ticker} at alert level {alert_level}. Updating close price from {last_close} to {current_close}.")
        else:
            # Handle alerts based on static price levels
            alert_level = float(alert_level)
            logger.info(f"chat_id: {chat_id}: Checking alert_id {alert_id} at alert level {alert_level} for {ticker} at last close {last_close} and current close {current_close}")
            
            # Trigger alert if the current price crosses the static alert level
            if (last_close < alert_level and current_close > alert_level) or (last_close > alert_level and current_close < alert_level):
                bot.send_message(chat_id, f"Alert triggered for {ticker}! Current close price {current_close} has crossed alert level {alert_level}.")
                connection = database.connect()
                database.delete_alert(connection, alert_id)
                logger.info(f"chat_id: {chat_id}: Alert message sent for {ticker} at alert level {alert_level}. Alert deleted.")
            else:
                # Update the last close price if no alert was triggered
                connection = database.connect()
                database.update_close_price(connection, alert_id, current_close)
                logger.info(f"chat_id: {chat_id}: Alert not triggered for {ticker} at alert level {alert_level}. Updating close price from {last_close} to {current_close}.")
    
    logger.info("End")

if __name__ == "__main__":
    main()
