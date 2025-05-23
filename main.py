
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
        await update.message.reply_text("Send the cleared PDF and I'll fill it step-by-step.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Upload a PDF. I’ll ask questions and return a completed version.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        USER_STATES.pop(update.effective_user.id, None)
        await update.message.reply_text("Cancelled.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer()

    def random_badge(self):
        return f"{random.randint(10000, 99999)}/{random.choice(['Leo Tanner', 'Riley Fox', 'Sam Carter'])}"

    def random_title_number(self):
        return f"C2025-0{random.randint(1000000, 9999999)}"

    def next_weekday(self, dt):
        dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.replace(hour=10, minute=0, second=0, microsecond=0)

    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        await file.download_to_drive(temp_file.name)
        await update.message.reply_text("Enter First Name:")
        USER_STATES[update.effective_user.id] = {"step": "awaiting_first", "pdf_path": temp_file.name}

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        text = update.message.text.strip()
        state = USER_STATES.get(uid, {})
        step = state.get("step")

        if step == "awaiting_first":
            state["first"] = text
            state["step"] = "awaiting_last"
            await update.message.reply_text("Enter Last Name:")
        elif step == "awaiting_last":
            state["last"] = text
            state["step"] = "awaiting_email"
            await update.message.reply_text("Enter Email:")
        elif step == "awaiting_email":
            state["email"] = text
            state["step"] = "awaiting_tracking"
            await update.message.reply_text("Enter Tracking Number:")
        elif step == "awaiting_tracking":
            state["tracking"] = text
            state["step"] = "awaiting_order_total"
            await update.message.reply_text("Enter Order Total (just numbers):")
        elif step == "awaiting_order_total":
            state["order_total"] = text
            state["step"] = "awaiting_address"
            await update.message.reply_text("Enter Full Address (e.g., 12 Medici Court, SCARBOROUGH, ON M1K5A4):")
        elif step == "awaiting_address":
            state["address"] = text
            state["step"] = "awaiting_delivery_dt"
            await update.message.reply_text("Enter Delivery Date and Time (e.g., 2025-05-21 02:15 PM):")
        elif step == "awaiting_delivery_dt":
            try:
                dt = datetime.strptime(text, "%Y-%m-%d %I:%M %p")
                state["delivery_dt"] = dt
                state["report_dt"] = self.next_weekday(dt)
                state["badge"] = self.random_badge()
                state["title"] = self.random_title_number()
                await self.apply_overlay(update, context, state)
            except Exception as e:
                await update.message.reply_text("Invalid format. Use: YYYY-MM-DD 02:15 PM (12H with leading zero).")

    async def apply_overlay(self, update: Update, context: ContextTypes.DEFAULT_TYPE, d):
        path = d["pdf_path"]
        out_path = path.replace(".pdf", "_done.pdf")
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        can.setFont("Helvetica-Bold", 10)

        # Draw each field precisely
        can.drawString(188, 730, d["title"])
        can.drawString(145, 543, d["first"])
        can.drawString(92, 543, d["last"])
        can.drawString(135, 439, d["email"])
        can.drawString(142, 505, d["tracking"])
        can.drawString(440, 505, d["badge"])
        can.drawString(405, 685, d["order_total"])
        can.drawString(118, 582, d["address"])
        can.drawString(290, 610, d["delivery_dt"].strftime("%Y-%m-%d %I:%M %p"))
        can.drawString(415, 610, d["report_dt"].strftime("%Y-%m-%d %I:%M %p"))
        can.drawString(460, 50, d["report_dt"].strftime("%Y-%m-%d %I:%M %p"))
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

        with open(out_path, "wb") as f:
            writer.write(f)

        await update.message.reply_document(document=open(out_path, "rb"), filename="completed_report.pdf")

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = PdfEditorBot(token)
    bot.run()
