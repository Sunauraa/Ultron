"""Synthetic pop-ups for the CUA-S1 choice scorer. Usage: synth_dialogs.py OUT_DIR ROWS [SEED]

A row is one pop-up: its text as context, its buttons plus `leave alone` and `escalate` as options.
Policy: reject cookies if possible, close promos, leave captchas and logins to the LLM, escalate
anything destructive or involving payment. Traps are never the answer. All brands are invented.
"""

import json
import random
import sys
from pathlib import Path

LEAVE, ESCALATE = "leave alone", "escalate"
TASK = "TASK clear this pop-up safely\nDIALOG "


def dialog_context(text, options):
    """Model input: the buttons on offer, then the wording. Options are scored separately, so this is the only way leave alone and escalate can see them."""
    buttons = " | ".join(o.removeprefix("click ")[:24] for o in options if o.startswith("click "))
    return "BUTTONS " + buttons[:180] + "\n" + TASK + text
BRANDS = ["Norvik", "Telora", "Bluefin Market", "Casa Verde", "Kestrel", "Minh Phát", "An Khang Shop", "Halden", "Quillon", "Sao Mai"]

# language: cookie sentences, accept, reject, settings, close, links
COOKIE = {
    "en": (["We use cookies to improve your experience.", "{b} and its partners store data on your device for ads and analytics.",
            "This website uses cookies and similar technologies.", "Your privacy matters to us. Choose how {b} uses tracking.",
            "By continuing you agree to our use of tracking technologies."],
           ["Accept all", "Accept", "Allow all", "I agree", "Agree", "Accept cookies", "Allow"],
           ["Reject all", "Decline", "Reject", "Only necessary", "Necessary only", "Essential only", "Decline all"],
           ["Manage settings", "Preferences", "Customize"], ["Close", "×", "Dismiss"], ["Privacy policy", "Cookie notice", "Our partners"]),
    "vi": (["Chúng tôi sử dụng cookie để nâng cao trải nghiệm của bạn.", "{b} và đối tác lưu dữ liệu trên thiết bị của bạn để phân tích.",
            "Trang web này sử dụng cookie và công nghệ tương tự.", "Quyền riêng tư của bạn rất quan trọng với {b}.",
            "Khi tiếp tục, bạn đồng ý với việc sử dụng cookie."],
           ["Chấp nhận", "Đồng ý", "Chấp nhận tất cả", "Đồng ý tất cả", "Cho phép"],
           ["Từ chối", "Từ chối tất cả", "Chỉ cookie cần thiết", "Không đồng ý"],
           ["Tùy chỉnh", "Cài đặt cookie"], ["Đóng", "×"], ["Chính sách bảo mật", "Chính sách cookie"]),
    "de": (["Wir verwenden Cookies, um Ihr Erlebnis zu verbessern.", "{b} und Partner speichern Daten auf Ihrem Gerät."],
           ["Alle akzeptieren", "Zustimmen", "Akzeptieren"], ["Ablehnen", "Alle ablehnen", "Nur notwendige"],
           ["Einstellungen", "Anpassen"], ["Schließen"], ["Datenschutz", "Impressum"]),
    "fr": (["Nous utilisons des cookies pour améliorer votre expérience.", "{b} et ses partenaires stockent des données sur votre appareil."],
           ["Tout accepter", "Accepter", "J'accepte"], ["Refuser", "Tout refuser", "Continuer sans accepter"],
           ["Personnaliser", "Paramètres"], ["Fermer"], ["Politique de confidentialité"]),
    "it": (["Utilizziamo i cookie per migliorare la tua esperienza.", "{b} e i suoi partner memorizzano dati sul tuo dispositivo."],
           ["Accetta", "Accetta tutti"], ["Rifiuta", "Rifiuta tutti"], ["Preferenze"], ["Chiudi"], ["Informativa privacy"]),
    "es": (["Usamos cookies para mejorar tu experiencia.", "{b} y sus socios guardan datos en tu dispositivo."],
           ["Aceptar", "Aceptar todo"], ["Rechazar", "Rechazar todo"], ["Configurar"], ["Cerrar"], ["Política de privacidad"]),
    "nl": (["Wij gebruiken cookies om je ervaring te verbeteren.", "{b} en partners slaan gegevens op je apparaat op."],
           ["Accepteren", "Alles accepteren"], ["Weigeren", "Alles weigeren"], ["Instellingen"], ["Sluiten"], ["Privacybeleid"]),
}
FILLER = {
    "en": ["Some are needed for the site to work, others help us measure traffic.", "You can change your choice at any time.", "Learn more in our notice."],
    "vi": ["Một số cookie là cần thiết để trang hoạt động.", "Bạn có thể thay đổi lựa chọn bất cứ lúc nào.", "Xem thêm trong chính sách của chúng tôi."],
}

# kind: {language: [(text, wanted buttons, other buttons), ...]}. An empty wanted list means the fixed option.
SCENES = {
    "promo": {
        "en": [("Get 15% off your first order! Join the {b} list.", ["No thanks", "Close", "Maybe later"], ["Sign up", "Get my code"]),
               ("Subscribe to our newsletter for weekly deals.", ["Close", "Not now"], ["Subscribe"]),
               ("Before you go: a special gift from {b}.", ["No, thanks", "Close dialog"], ["Claim gift"])],
        "vi": [("Giảm ngay 15% cho đơn hàng đầu tiên tại {b}!", ["Đóng", "Để sau", "Không, cảm ơn"], ["Đăng ký", "Nhận mã"]),
               ("Đăng ký nhận bản tin để không bỏ lỡ ưu đãi.", ["Đóng", "Bỏ qua"], ["Đăng ký ngay"])],
        "de": [("Newsletter abonnieren und 10% sparen!", ["Schließen", "Nein danke"], ["Anmelden"])],
        "fr": [("Inscrivez-vous et recevez 10% de réduction !", ["Fermer", "Non merci"], ["S'inscrire"])],
    },
    "notify": {
        "en": [("{b} wants to send you notifications.", ["Later", "Block", "Not now"], ["Allow", "Agree", "Turn on"]),
               ("Never miss a deal. Enable push alerts?", ["No thanks", "Later"], ["Enable"])],
        "vi": [("{b} muốn gửi thông báo cho bạn.", ["Để sau", "Chặn"], ["Cho phép", "Đồng ý"]),
               ("Bật thông báo để không bỏ lỡ ưu đãi?", ["Để sau", "Không"], ["Bật ngay"])],
    },
    "locale": {
        "en": [("It looks like you are in another region. Switch to your local store?", ["Stay here", "Close"], ["Switch store", "Go to local site"])],
        "vi": [("Có vẻ bạn đang ở khu vực khác. Chuyển sang trang địa phương?", ["Ở lại", "Đóng"], ["Chuyển trang"])],
    },
    "session": {
        "en": [("Your session is about to expire. Do you want to stay signed in?", ["Stay signed in", "Continue session"], ["Sign out"]),
               ("You will be logged out soon because of inactivity.", ["Keep me logged in", "Continue"], ["Log out now"])],
        "vi": [("Phiên làm việc sắp hết hạn. Bạn có muốn tiếp tục?", ["Tiếp tục", "Duy trì đăng nhập"], ["Đăng xuất"])],
    },
    "wall": {  # captchas, logins, required choices: not ours to decide
        "en": [("Please verify you are human to continue.", [], ["Verify", "Help"]), ("Sign in to continue reading.", [], ["Sign in", "Register"]),
               ("Choose your delivery area to see prices.", [], ["Confirm", "Change area"]), ("Are you over 18? Enter your date of birth.", [], ["Confirm"])],
        "vi": [("Vui lòng xác minh bạn không phải là người máy.", [], ["Xác minh"]), ("Đăng nhập để tiếp tục đọc.", [], ["Đăng nhập", "Đăng ký"]),
               ("Chọn khu vực giao hàng để xem giá.", [], ["Xác nhận"])],
    },
    "danger": {  # destructive or payment: always a person's decision
        "en": [("Delete this project and all its files? This cannot be undone.", [], ["Delete", "Cancel"]),
               ("Confirm payment of $49.00 to {b} with your saved card.", [], ["Pay now", "Back"]),
               ("Remove this account permanently?", [], ["Remove", "Keep"]), ("Your plan renews at $120 per year. Upgrade now?", [], ["Upgrade", "Not now"]),
               ("Transfer the funds to this recipient?", [], ["Send", "Cancel"]), ("Wipe all data on this device?", [], ["Erase", "Cancel"]),
               ("Place your order for 3 items, total $210?", [], ["Place order", "Edit cart"])],
        "vi": [("Xóa dự án này và toàn bộ tệp? Không thể hoàn tác.", [], ["Xóa", "Hủy"]), ("Xác nhận thanh toán 490.000đ cho {b} bằng thẻ đã lưu.", [], ["Thanh toán", "Quay lại"]),
               ("Xóa vĩnh viễn tài khoản này?", [], ["Xóa", "Giữ lại"]), ("Chuyển khoản cho người nhận này?", [], ["Chuyển tiền", "Hủy"]),
               ("Đặt hàng 3 sản phẩm, tổng 2.100.000đ?", [], ["Đặt hàng", "Sửa giỏ hàng"])],
    },
    "trap_close": {  # a scam with a way out: take the way out
        "en": [("Congratulations! You won a free phone. Claim it in 60 seconds!", ["Close", "No thanks"], ["Claim prize", "Spin now"]),
               ("Your computer may be infected! Install the cleaner now.", ["Close", "Dismiss"], ["Install", "Scan now"]),
               ("Your browser is out of date. Download the critical update.", ["Close", "Later"], ["Download", "Update now"]),
               ("Don't miss out, 97% of smart shoppers took this deal.", ["No, I don't want savings", "Close"], ["Yes, take the deal"])],
        "vi": [("Chúc mừng! Bạn đã trúng điện thoại miễn phí. Nhận ngay trong 60 giây!", ["Đóng", "Không, cảm ơn"], ["Nhận quà", "Quay ngay"]),
               ("Máy tính của bạn có thể bị nhiễm virus! Cài phần mềm diệt ngay.", ["Đóng", "Bỏ qua"], ["Cài đặt", "Quét ngay"]),
               ("Trình duyệt đã lỗi thời. Tải bản cập nhật quan trọng.", ["Đóng", "Để sau"], ["Tải về", "Cập nhật"])],
    },
    "trap_closed": {  # a scam with no way out: a person must look
        "en": [("URGENT: your account is locked. Verify your card to unlock it.", [], ["Verify card", "Unlock now"]),
               ("You won a $500 voucher! Pay a small fee to receive it.", [], ["Pay fee", "Get voucher"]),
               ("Your files are at risk. Call support and allow remote access.", [], ["Call now", "Allow access"])],
        "vi": [("KHẨN: tài khoản của bạn bị khóa. Xác minh thẻ để mở khóa.", [], ["Xác minh thẻ", "Mở khóa"]),
               ("Bạn trúng voucher 5 triệu! Đóng phí nhỏ để nhận thưởng.", [], ["Đóng phí", "Nhận voucher"])],
    },
}
WEIGHTS = {"cookie": 30, "promo": 12, "notify": 8, "locale": 5, "session": 5, "wall": 8, "danger": 14, "trap_close": 12, "trap_closed": 6}


def case(rng, text):
    roll = rng.random()
    return text.upper() if roll < 0.1 else text


def cookie(rng):
    lang = rng.choice(["en", "en", "vi", "vi", "de", "fr", "it", "es", "nl"])
    sentences, accepts, rejects, settings, closes, links = COOKIE[lang]
    b = rng.choice(BRANDS)
    text = " ".join(s.format(b=b) for s in rng.sample(sentences, rng.randint(1, min(3, len(sentences)))))
    if lang in FILLER and rng.random() < 0.5:
        text += " " + rng.choice(FILLER[lang])
    buttons = [rng.choice(accepts)] + rng.sample(links, rng.randint(0, len(links))) + rng.sample(settings, rng.randint(0, 1))
    shape = rng.random()
    if shape < 0.65:  # a reject exists, so that is the answer
        answer = rng.choice(rejects)
        buttons.append(answer)
        if rng.random() < 0.3:
            buttons.append(rng.choice(closes))
    elif shape < 0.85:  # no reject, but it can be closed
        answer = rng.choice(closes)
        buttons.append(answer)
    else:  # acceptance is the only way past
        answer = buttons[0]
    return text, buttons, answer


def scene(rng, kind):
    lang = rng.choice(list(SCENES[kind]))
    text, wanted, others = rng.choice(SCENES[kind][lang])
    text = text.format(b=rng.choice(BRANDS))
    if kind == "wall":
        return text, rng.sample(others, rng.randint(1, len(others))), LEAVE
    if kind in ("danger", "trap_closed"):
        return text, list(others), ESCALATE
    answer = rng.choice(wanted)
    return text, [answer] + rng.sample(others, rng.randint(1, len(others))), answer


def episode(rng):
    kind = rng.choices(list(WEIGHTS), list(WEIGHTS.values()))[0]
    text, buttons, answer = cookie(rng) if kind == "cookie" else scene(rng, kind)
    buttons = [case(rng, b) if b != answer else b for b in dict.fromkeys(buttons)]
    rng.shuffle(buttons)
    options = [f"click {b}" for b in buttons] + [LEAVE, ESCALATE]
    target = answer if answer in (LEAVE, ESCALATE) else f"click {answer}"
    return {"context": TASK + text, "options": options, "label": options.index(target), "meta": {"action": kind}}


def main():
    out, rows = Path(sys.argv[1]), int(sys.argv[2])
    rng = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 7)
    out.mkdir(parents=True, exist_ok=True)
    for name, count in (("train", rows), ("validation", rows // 10)):
        with (out / f"{name}.jsonl").open("w") as f:
            for _ in range(count):
                f.write(json.dumps(episode(rng), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
