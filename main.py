
import os
import random
import re
from datetime import datetime, timedelta
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

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

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("welcome !")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("upload a PDF and I’ll guide you through editing it.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        USER_STATE.pop(update.effective_user.id, None)
        await update.message.reply_text("cancelled.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()

    def generate_report_number(self):
        return f"C{datetime.now().year}-0{random.randint(1000000, 9999999)}"

    def next_weekday(self, dt):
        dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.replace(hour=10, minute=0)

    def clean_datetime_string(self, text):
        cleaned = text.strip()
        cleaned = re.sub(r"[\u200b\u200c\u202f\ufeff\xa0]", "", cleaned)
        cleaned = re.sub(r"[“”]", '"', cleaned)
        cleaned = re.sub(r"[‘’]", "'", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.upper()

    def try_parse_datetime(self, text):
        formats = [
            "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M%p",
            "%Y-%m-%d %I:%M", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M%p"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except:
                continue
        return None

    async def handle_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        file = await context.bot.get_file(update.message.document.file_id)
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        await file.download_to_drive(tf.name)
        USER_STATE[update.effective_user.id] = {"step": "awaiting_first", "pdf_path": tf.name}
        await update.message.reply_text("first name:")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            cleaned = self.clean_datetime_string(msg)
            delivery = self.try_parse_datetime(cleaned)
            if delivery:
                report_dt = self.next_weekday(delivery)
                report_number = self.generate_report_number()
                state.update({
                    "delivery_dt": delivery,
                    "report_dt": report_dt,
                    "report_number": report_number
                })
                await self.fill_pdf(update, context, state)
            else:
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
            "Report Number": data["report_number"]
        }

        writer.update_page_form_field_values(writer.pages[0], fields)

        os.makedirs("/mnt/data", exist_ok=True)
        filled_pdf_path = f"/mnt/data/filled-{data['report_number']}.pdf"
        with open(filled_pdf_path, "wb") as f:
            writer.write(f)

        # Overlay Report Created footer and Report Number title
        final_path = f"/mnt/data/report-{data['report_number']}.pdf"
        c = canvas.Canvas(final_path, pagesize=letter)
        width, height = letter

        c.setFont("Helvetica", 8)
        c.drawString(40, 21.5, f"Report Created On {data['report_dt'].strftime('%Y-%m-%d %I:%M %p')}")
        right_text = "Page 1 of 1"
        right_width = c.stringWidth(right_text, "Helvetica", 8)
        c.drawString(width - right_width - 40, 21.5, right_text)

        c.setFont("Helvetica-Bold", 10)
        title_text = data['report_number']
        title_width = c.stringWidth(title_text, "Helvetica-Bold", 10)
        c.drawString((width - title_width) / 2, height - 129, title_text)

        c.save()

        with open(final_path, "rb") as final_file:
            await update.message.reply_document(document=final_file, filename=f"report-{data['report_number']}.pdf")

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    PDFEditorBot(token).run()
