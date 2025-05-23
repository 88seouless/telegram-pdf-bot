
import os
import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import tempfile
import logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

USER_STATES = {}

class PdfEditorBot:
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
        await update.message.reply_text("Send me your cleared PDF and I’ll walk you through filling it.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Upload a blank PDF form. I’ll prompt you for details and generate a filled version.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        USER_STATES.pop(update.effective_user.id, None)
        await update.message.reply_text("Cancelled.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer()

    def random_badge(self):
        return f"{random.randint(10000, 99999)}/{random.choice(['Leo Tanner', 'Riley Fox', 'Sam Carter'])}"

    def random_title_number(self):
        return f"C2025-0{random.randint(1000000, 9999999)}"

    def next_weekday(self, delivery_datetime):
        next_day = delivery_datetime + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip Sat/Sun
            next_day += timedelta(days=1)
        return next_day.replace(hour=10, minute=0, second=0, microsecond=0)

    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        await file.download_to_drive(temp_file.name)
        await update.message.reply_text("Enter First Name:")
        USER_STATES[update.effective_user.id] = {
            "step": "awaiting_first",
            "pdf_path": temp_file.name
        }

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        text = update.message.text.strip()
        user = USER_STATES.get(uid, {})
        step = user.get("step")

        if step == "awaiting_first":
            user["first"] = text
            user["step"] = "awaiting_last"
            await update.message.reply_text("Enter Last Name:")
        elif step == "awaiting_last":
            user["last"] = text
            user["step"] = "awaiting_email"
            await update.message.reply_text("Enter Email:")
        elif step == "awaiting_email":
            user["email"] = text
            user["step"] = "awaiting_tracking"
            await update.message.reply_text("Enter Tracking Number:")
        elif step == "awaiting_tracking":
            user["tracking"] = text
            user["step"] = "awaiting_order_total"
            await update.message.reply_text("What was the order total?")
        elif step == "awaiting_order_total":
            user["order_total"] = text
            user["step"] = "awaiting_delivery_datetime"
            await update.message.reply_text("Enter delivery date & time (e.g. 2025-05-21 2:15 PM):")
        elif step == "awaiting_delivery_datetime":
            try:
                delivery_dt = datetime.strptime(text, "%Y-%m-%d %I:%M %p")
                user["delivery_dt"] = delivery_dt
                user["report_dt"] = self.next_weekday(delivery_dt)
                user["badge"] = self.random_badge()
                user["title"] = self.random_title_number()
                await self.apply_overlay(update, context, user)
            except Exception as e:
                await update.message.reply_text("Invalid format. Please use: YYYY-MM-DD H:MM AM/PM")

    async def apply_overlay(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data):
        path = data["pdf_path"]
        output_path = path.replace(".pdf", "_done.pdf")
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        can.setFont("Helvetica-Bold", 10)

        # Overlay coordinates (estimates based on field positioning)
        can.drawString(145, 543, data["first"])
        can.drawString(92, 543, data["last"])
        can.drawString(135, 439, data["email"])
        can.drawString(142, 505, data["tracking"])
        can.drawString(440, 505, data["badge"])
        can.drawString(405, 685, data["order_total"])
        can.drawString(290, 610, data["delivery_dt"].strftime("%Y-%m-%d %I:%M %p"))
        can.drawString(415, 610, data["report_dt"].strftime("%Y-%m-%d %I:%M %p"))
        can.drawString(460, 50, data["report_dt"].strftime("%Y-%m-%d %I:%M %p"))
        can.setFont("Helvetica-Bold", 12)
        can.drawString(188, 730, data["title"])
        can.save()
        packet.seek(0)

        new_pdf = PdfReader(packet)
        original = PdfReader(path)
        writer = PdfWriter()

        for i in range(len(original.pages)):
            page = original.pages[i]
            if i == 0:
                page.merge_page(new_pdf.pages[0])
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

        await update.message.reply_document(document=open(output_path, "rb"), filename="edited.pdf")

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = PdfEditorBot(token)
    bot.run()
