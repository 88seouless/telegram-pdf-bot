
import os
import random
import re
import tempfile
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from adobe.pdfservices.operation.auth.credentials import Credentials
from adobe.pdfservices.operation.execution_context import ExecutionContext
from adobe.pdfservices.operation.io.file_ref import FileRef
from adobe.pdfservices.operation.pdfops.options.document_merge.document_merge_options import DocumentMergeOptions
from adobe.pdfservices.operation.pdfops.document_merge_operation import DocumentMergeOperation
from adobe.pdfservices.operation.pdfops.options.document_merge.merge_field import MergeField
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException

USER_STATE = {}

class PDFEditorBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(MessageHandler(filters.Document.PDF, self.handle_pdf))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("welcome !")

    def generate_report_number(self):
        return f"C{datetime.now().year}-0{random.randint(1000000, 9999999)}"

    def next_weekday(self, dt):
        dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.replace(hour=10, minute=0)

    def clean_datetime_string(self, text):
        cleaned = text.strip()
        cleaned = re.sub(r"[​‌ ﻿ ]", "", cleaned)
        cleaned = re.sub(r"[“”]", '"', cleaned)
        cleaned = re.sub(r"[‘’]", "'", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.upper()

    def try_parse_datetime(self, text):
        formats = [
            "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M%p"
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
        USER_STATE[update.effective_user.id] = {
            "step": "awaiting_first",
            "pdf_path": tf.name
        }
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
            await update.message.reply_text("delivery date and time (e.g. 2025-05-24 02:15 PM):")
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
        try:
            credentials = Credentials.service_account_credentials_builder()                 .from_file("pdfservices-api-credentials.json")                 .build()

            execution_context = ExecutionContext.create(credentials)

            input_pdf = FileRef.create_from_local_file(data["pdf_path"])

            json_data = {
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

            options = DocumentMergeOptions(json_data, output_format="pdf")
            operation = DocumentMergeOperation.create_new()
            operation.set_input(input_pdf)
            operation.set_options(options)

            result = operation.execute(execution_context)
            output_path = f"/mnt/data/report-{data['report_number']}.pdf"
            result.save_as(output_path)

            await update.message.reply_document(document=open(output_path, "rb"), filename=f"report-{data['report_number']}.pdf")

        except Exception as e:
            await update.message.reply_text(f"Adobe PDF generation failed: {str(e)}")

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    PDFEditorBot(token).run()
