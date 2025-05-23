import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import random
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
        await update.message.reply_text("Welcome! Send me a PDF and I’ll guide you through editing it.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Upload a PDF, and I’ll ask for some text to fill it in!")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        USER_STATES.pop(update.effective_user.id, None)
        await update.message.reply_text("Cancelled.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.callback_query.answer()

    def random_badge(self):
        number = f"{random.randint(10000, 99999)}"
        name = random.choice(["Sam Carter", "Riley Fox", "Chris Nolan", "Drew Martin"])
        return f"{number}/{name}"

    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        await file.download_to_drive(temp_file.name)
        await update.message.reply_text("Enter the First Name:")
        USER_STATES[update.effective_user.id] = {"step": "awaiting_first_name", "pdf_path": temp_file.name}

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_state = USER_STATES.get(user_id, {})
        if not user_state:
            await update.message.reply_text("Upload a PDF first.")
            return
        step = user_state.get("step")
        text = update.message.text.strip()
        if step == "awaiting_first_name":
            user_state["first_name"] = text
            user_state["step"] = "awaiting_last_name"
            await update.message.reply_text("Enter the Last Name:")
        elif step == "awaiting_last_name":
            user_state["last_name"] = text
            user_state["step"] = "awaiting_email"
            await update.message.reply_text("Enter the Email:")
        elif step == "awaiting_email":
            user_state["email"] = text
            user_state["step"] = "awaiting_tracking"
            await update.message.reply_text("Enter the Tracking Number:")
        elif step == "awaiting_tracking":
            user_state["tracking"] = text
            user_state["badge"] = self.random_badge()
            await self.apply_text_overlay(update, context, user_state)

    async def apply_text_overlay(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
        output_path = data["pdf_path"].replace(".pdf", "_filled.pdf")
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        can.drawString(145, 543, data["first_name"])
        can.drawString(92, 543, data["last_name"])
        can.drawString(135, 439, data["email"])
        can.drawString(142, 505, data["tracking"])
        can.drawString(440, 505, data["badge"])
        can.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
        existing_pdf = PdfReader(data["pdf_path"])
        output = PdfWriter()
        for i in range(len(existing_pdf.pages)):
            page = existing_pdf.pages[i]
            if i == 0:
                page.merge_page(new_pdf.pages[0])
            output.add_page(page)
        with open(output_path, "wb") as f_out:
            output.write(f_out)
        await update.message.reply_document(document=open(output_path, "rb"), filename="filled_form.pdf")

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = PdfEditorBot(token)
    bot.run()
