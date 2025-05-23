
import os
import random
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NameObject, TextStringObject
import tempfile
import logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

USER_STATE = {}

class PDFEditorBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("cancel", self.cancel))
        self.app.add_handler(MessageHandler(filters.Document.PDF, self.handle_pdf))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("welcome !")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Upload a PDF and I'll guide you through filling it.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        USER_STATE.pop(update.effective_user.id, None)
        await update.message.reply_text("cancelled.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer()

    def generate_report_number(self):
        year = datetime.now().year
        suffix = f"0{random.randint(1000000, 9999999)}"
        return f"C{year}-{suffix}"

    def next_weekday(self, dt):
        dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.replace(hour=10, minute=0)

    def clean_datetime_string(self, text):
        cleaned = text.strip()
        cleaned = re.sub(r"[\u200b\u200c\u202f\ufeff\xa0]", "", cleaned)
        cleaned = re.sub(r"[“”]", '"', cleaned)  # smart quotes
        cleaned = re.sub(r"[‘’]", "'", cleaned)  # smart apostrophes
        cleaned = re.sub(r"\s+", " ", cleaned)  # normalize all whitespace
        cleaned = cleaned.upper()
        return cleaned

    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        await file.download_to_drive(temp_file.name)
        await update.message.reply_text("first name:")
        USER_STATE[update.effective_user.id] = {
            "step": "awaiting_first",
            "pdf_path": temp_file.name
        }

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        msg = update.message.text.strip()
        state = USER_STATE.get(uid, {})
        step = state.get("step")

        if step == "awaiting_first":
            state["first_name"] = msg
            state["step"] = "awaiting_last"
            await update.message.reply_text("last name:")
        elif step == "awaiting_last":
            state["last_name"] = msg
            state["step"] = "awaiting_email"
            await update.message.reply_text("email:")
        elif step == "awaiting_email":
            state["email"] = msg
            state["step"] = "awaiting_tracking"
            await update.message.reply_text("tracking number:")
        elif step == "awaiting_tracking":
            state["tracking"] = msg
            state["step"] = "awaiting_order_total"
            await update.message.reply_text("order total:")
        elif step == "awaiting_order_total":
            state["order_total"] = msg
            state["step"] = "awaiting_address"
            await update.message.reply_text("address:")
        elif step == "awaiting_address":
            state["address"] = msg
            state["step"] = "awaiting_delivery"
            await update.message.reply_text("delivery date and time:")
        elif step == "awaiting_delivery":
            try:
                clean_text = self.clean_datetime_string(msg)
                delivery = datetime.strptime(clean_text, "%Y-%m-%d %I:%M %p")
                report_dt = self.next_weekday(delivery)
                report_number = self.generate_report_number()

                state["delivery_dt"] = delivery
                state["report_dt"] = report_dt
                state["report_number"] = report_number

                await self.fill_pdf(update, context, state)
            except Exception:
                await update.message.reply_text("invalid format. use: 2025-05-23 02:15 PM")

    async def fill_pdf(self, update, context, data):
        reader = PdfReader(data["pdf_path"])
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        fields = {
            "FIRST NAME": data["first_name"],
            "LAST NAME": data["last_name"],
            "EMAIL": data["email"],
            "TRACKING NUMBER": data["tracking"],
            "ORDERTOTAL": data["order_total"],
            "ADDRESS": data["address"],
            "DATE TIME REPORTED": data["report_dt"].strftime("%Y-%m-%d %I:%M %p"),
            "DATETIME STARTED": data["delivery_dt"].strftime("%Y-%m-%d %I:%M %p"),
            "Report Number": data["report_number"],
            "report created on": data["report_dt"].strftime("%Y-%m-%d %I:%M %p"),
        }

        writer.update_page_form_field_values(writer.pages[0], fields)

        output_name = f"report-{data['report_number']}.pdf"
        out_path = os.path.join("/mnt/data", output_name)

        with open(out_path, "wb") as f:
            writer.write(f)

        await update.message.reply_document(document=open(out_path, "rb"), filename=output_name)

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = PDFEditorBot(token)
    bot.run()
