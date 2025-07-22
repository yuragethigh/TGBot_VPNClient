from dotenv import load_dotenv
import os

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # 3x-ui 
    XUI_URL = os.getenv("XUI_URL")
    XUI_USERNAME = os.getenv("XUI_USERNAME")
    XUI_PASSWORD = os.getenv("XUI_PASSWORD")
    XUI_INBOUND_ID = int(os.getenv("XUI_INBOUND_ID", "1"))
    XUI_IGNORE_SSL = os.getenv("XUI_IGNORE_SSL", "1") == "1"  

    # DATA FOR VLESS LINK
    LINK_HOST = os.getenv("LINK_HOST", "212.69.84.243")
    LINK_PORT = int(os.getenv("LINK_PORT", "443"))
    LINK_TAG_PREFIX = os.getenv("LINK_TAG_PREFIX", "Home")

    VLESS_PBK = os.getenv("VLESS_PBK")
    VLESS_FP = os.getenv("VLESS_FP")
    VLESS_SNI = os.getenv("VLESS_SNI")
    VLESS_SID = os.getenv("VLESS_SID")
    VLESS_SPX = os.getenv("VLESS_SPX")
    VLESS_FLOW = os.getenv("VLESS_FLOW") 


    # YooKassa
    YK_SHOP_ID = os.getenv("YK_SHOP_ID")
    YK_SECRET_KEY = os.getenv("YK_SECRET_KEY")
    YK_RETURN_URL = os.getenv("YK_RETURN_URL")

    # Тарифы
    PLAN_MONTH_PRICE = int(os.getenv("PLAN_MONTH_PRICE", "399"))
    PLAN_MONTH_DAYS = int(os.getenv("PLAN_MONTH_DAYS", "30"))
    PLAN_3MONTH_PRICE = int(os.getenv("PLAN_3MONTH_PRICE", "1000"))
    PLAN_3MONTH_DAYS = int(os.getenv("PLAN_3MONTH_DAYS", "90"))
