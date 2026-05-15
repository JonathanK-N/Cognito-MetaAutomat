import os
import tempfile
import requests
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY")
FB_PAGE_TOKEN  = os.environ.get("FB_PAGE_TOKEN")
FB_PAGE_ID     = os.environ.get("FB_PAGE_ID")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def generate_caption(image_url: str, hint: str = "") -> str:
    prompt = f"""Tu es un community manager sympathique et créatif.
Écris un texte de publication Facebook chaleureux et attrayant pour cette image.
{f"Contexte : {hint}" if hint else ""}

Règles :
- Ton amical, proche des gens, comme un ami qui partage quelque chose
- Commence par une accroche fun ou une question engageante
- 2 à 4 phrases max, légères et naturelles
- Termine avec un appel à l'action simple (ex : "Dis-nous ce que tu en penses 👇")
- 3 à 5 emojis bien placés
- 3 hashtags pertinents à la fin

Réponds uniquement avec le texte, sans explication."""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    return response.content[0].text

def post_to_facebook(image_url: str, caption: str) -> dict:
    img_data = requests.get(image_url, timeout=30).content
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(img_data)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        r = requests.post(
            f"https://graph.facebook.com/{FB_PAGE_ID}/photos",
            data={"caption": caption, "access_token": FB_PAGE_TOKEN},
            files={"source": f},
            timeout=30
        )
    os.unlink(tmp_path)
    return r.json()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Accès non autorisé.")
        return

    await update.message.reply_text("📸 Photo reçue ! Je prépare ton post...")

    try:
        photo   = update.message.photo[-1]
        file    = await context.bot.get_file(photo.file_id)
        img_url = file.file_path
        hint    = update.message.caption or ""

        caption = generate_caption(img_url, hint)

        await update.message.reply_text(
            f"✍️ Voici le texte généré :\n\n{caption}\n\n"
            f"Réponds *OUI* pour publier, ou envoie un texte pour le modifier.",
            parse_mode="Markdown"
        )
        context.user_data["pending_caption"] = caption
        context.user_data["pending_image"]   = img_url

    except Exception as e:
        await update.message.reply_text(f"❌ Erreur lors de la génération : {e}")

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        return

    if "pending_caption" not in context.user_data:
        return

    text = update.message.text.strip().lower()

    if text == "oui":
        caption   = context.user_data["pending_caption"]
        image_url = context.user_data["pending_image"]
    else:
        caption   = update.message.text
        image_url = context.user_data["pending_image"]

    try:
        result = post_to_facebook(image_url, caption)
        context.user_data.clear()

        if "id" in result:
            await update.message.reply_text("🎉 Publié avec succès sur ta page Facebook !")
        else:
            await update.message.reply_text(f"❌ Erreur Facebook : {result}")

    except Exception as e:
        await update.message.reply_text(f"❌ Erreur lors de la publication : {e}")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN est vide. Vérifie tes variables dans Railway.")
if not ANTHROPIC_KEY:
    raise RuntimeError("❌ ANTHROPIC_KEY est vide. Vérifie tes variables dans Railway.")
if not FB_PAGE_TOKEN:
    raise RuntimeError("❌ FB_PAGE_TOKEN est vide. Vérifie tes variables dans Railway.")
if not FB_PAGE_ID:
    raise RuntimeError("❌ FB_PAGE_ID est vide. Vérifie tes variables dans Railway.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation))

print("✅ Variables OK — connexion à Telegram...")
app.run_polling()
