"""Ten hand-written local form tasks and the localhost server that hosts them.

Fields are (name, label, type, value) where value is the correct answer, or None if the
document has no value and the field must stay empty. `document` lists what the agent is given.
"""

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qsl


def text(name, label, value=None):
    return {"name": name, "label": label, "type": "text", "value": value}


def select(name, label, options, value):
    return {"name": name, "label": label, "type": "select", "options": options, "value": value}


def radio(name, label, options, value):
    return {"name": name, "label": label, "type": "radio", "options": options, "value": value}


def check(name, label, reveals=None):
    return {"name": name, "label": label, "type": "checkbox", "value": "on", "reveals": reveals}


def form(id, lang, title, pages, popup=False):
    return {"id": id, "lang": lang, "title": title, "pages": pages, "popup": popup}


FORMS = [
    form("contact", "en", "Contact us", [[
        text("name", "Full name", "Maria Lopez"),
        text("email", "Email address", "maria.lopez@example.com"),
        text("phone", "Phone number", "415-555-0132"),
        text("company", "Company", "Harbor Foods"),
        text("subject", "Subject", "Invoice question"),
    ]]),
    form("employee", "en", "Employee registration", [[
        text("first", "First name", "David"),
        text("last", "Last name", "Chen"),
        text("dob", "Date of birth", "04/12/1988"),
        text("email", "Work email", "d.chen@example.com"),
        text("phone", "Mobile phone", "206-555-0178"),
        text("street", "Street address", "88 Pine Street"),
        text("city", "City", "Seattle"),
        text("zip", "ZIP code", "98101"),
        text("title", "Job title", "Accountant"),
        text("fax", "Fax number"),
        check("agree", "I confirm this information is correct"),
    ]]),
    form("job", "en", "Job application", [[
        text("name", "Applicant name", "Priya Nair"),
        text("email", "Email", "priya.nair@example.com"),
        select("position", "Position", ["Analyst", "Engineer", "Manager"], "Engineer"),
        radio("type", "Employment type", ["Full-time", "Part-time", "Contract"], "Full-time"),
        text("years", "Years of experience", "6"),
        check("consent", "I consent to data processing"),
    ]]),
    form("shipping", "en", "Shipping wizard", [
        [text("name", "Recipient name", "Tom Becker"), text("phone", "Recipient phone", "312-555-0199")],
        [text("street", "Street", "500 Lake Avenue"), text("city", "City", "Chicago"),
         text("zip", "Postal code", "60601"), select("country", "Country", ["Canada", "Mexico", "United States"], "United States")],
        [radio("speed", "Delivery speed", ["Standard", "Express"], "Express"), text("notes", "Delivery notes", "Leave at front desk")],
    ]),
    form("loan", "en", "Business loan application", [[
        text("biz", "Business name", "Northwind Tools LLC"),
        text("ein", "Employer identification number", "12-3456789"),
        text("owner", "Owner name", "Sarah Kim"),
        text("email", "Contact email", "sarah@example.com"),
        text("phone", "Contact phone", "617-555-0144"),
        text("revenue", "Annual revenue", "850000"),
        text("amount", "Requested amount", "120000"),
        text("purpose", "Loan purpose", "Equipment purchase"),
        text("bank", "Bank name", "First Harbor Bank"),
        text("account", "Account number", "004477120"),
        text("referral", "Referral code"),
        text("broker", "Broker name"),
    ]]),
    form("popup", "en", "Newsletter sign-up", [[
        text("name", "Your name", "Alex Morgan"),
        text("email", "Your email", "alex.morgan@example.com"),
        select("topic", "Topic", ["News", "Offers", "Events"], "Events"),
    ]], popup=True),
    form("conditional", "en", "Vendor onboarding", [[
        text("vendor", "Vendor name", "Blue Ridge Supply"),
        text("contact", "Contact person", "Nina Patel"),
        text("email", "Contact email", "nina@example.com"),
        check("tax_exempt", "This vendor is tax exempt", reveals="cert"),
        text("cert", "Exemption certificate number", "EX-55821"),
    ]]),
    form("vi_employee", "vi", "Đăng ký nhân viên", [[
        text("name", "Họ và tên", "Nguyễn Văn An"),
        text("dob", "Ngày sinh", "14/03/1991"),
        text("cccd", "Số căn cước công dân", "079091000123"),
        text("email", "Thư điện tử", "an.nguyen@example.com"),
        text("phone", "Số điện thoại", "0912345678"),
        text("address", "Địa chỉ thường trú", "12 Lê Lợi, Quận 1"),
        text("city", "Thành phố", "Hồ Chí Minh"),
        text("title", "Chức danh", "Kế toán"),
        text("tax", "Mã số thuế", "0312345678"),
        text("fax", "Số fax"),
        check("agree", "Tôi xác nhận thông tin trên là đúng"),
    ]]),
    form("vi_wizard", "vi", "Đăng ký doanh nghiệp", [
        [text("biz", "Tên công ty", "Công ty TNHH An Phát"), text("tax", "Mã số thuế", "0398765432"),
         text("rep", "Người đại diện", "Trần Thị Bình")],
        [text("phone", "Số điện thoại", "0987654321"), text("email", "Thư điện tử", "binh@example.com"),
         select("city", "Tỉnh/Thành phố", ["Hà Nội", "Đà Nẵng", "Hồ Chí Minh"], "Đà Nẵng")],
    ]),
    form("vi_profile", "vi", "Hồ sơ khách hàng", [[
        text("name", "Họ tên khách hàng", "Lê Minh Tuấn"),
        text("phone", "Điện thoại liên hệ", "0901222333"),
        radio("gender", "Giới tính", ["Nam", "Nữ"], "Nam"),
        select("product", "Sản phẩm quan tâm", ["Tiết kiệm", "Vay mua nhà", "Thẻ tín dụng"], "Vay mua nhà"),
        text("bank", "Số tài khoản ngân hàng", "190333444555"),
        check("consent", "Tôi đồng ý với các điều khoản"),
    ]]),
]
BY_ID = {f["id"]: f for f in FORMS}
SUBMIT = {"en": ("Submit", "Next"), "vi": ("Gửi", "Tiếp theo")}


def document(f):
    """Render the source document the agent receives."""
    lines = []
    for page in f["pages"]:
        for field in page:
            if field["type"] == "checkbox":
                lines.append(f"{field['label']}: yes")
            elif field["value"] is not None:
                lines.append(f"{field['label']}: {field['value']}")
    return "\n".join(lines)


def gold(f):
    return {x["name"]: x["value"] for page in f["pages"] for x in page if x["value"] is not None}


def _field_html(x, hidden_names):
    name, label = x["name"], html.escape(x["label"])
    style = ' style="display:none"' if name in hidden_names else ""
    if x["type"] == "text":
        body = f'<input type="text" id="{name}" name="{name}">'
    elif x["type"] == "select":
        options = "".join(f"<option>{html.escape(o)}</option>" for o in x["options"])
        body = f'<select id="{name}" name="{name}"><option value="">--</option>{options}</select>'
    elif x["type"] == "radio":
        body = "".join(
            f'<label><input type="radio" name="{name}" value="{html.escape(o)}"> {html.escape(o)}</label> '
            for o in x["options"]
        )
        return f'<p id="row_{name}"{style}><span>{label}</span> {body}</p>'
    else:
        reveal = ""
        if x.get("reveals"):
            reveal = f" onchange=\"document.getElementById('row_{x['reveals']}').style.display=this.checked?'block':'none'\""
        return f'<p id="row_{name}"{style}><label><input type="checkbox" id="{name}" name="{name}"{reveal}> {label}</label></p>'
    return f'<p id="row_{name}"{style}><label for="{name}">{label}</label> {body}</p>'


POPUP = """<div id="pop" style="position:fixed;inset:0;background:rgba(0,0,0,.5)">
<div style="background:#fff;margin:80px auto;width:320px;padding:20px">
<p>We use cookies on this site.</p>
<button type="button" onclick="document.getElementById('pop').remove()">Accept cookies</button>
</div></div>"""


def _page_html(f, index):
    pages = f["pages"]
    hidden = {x["reveals"] for x in pages[index] if x.get("reveals")}
    fields = "".join(_field_html(x, hidden) for x in pages[index])
    submit, nxt = SUBMIT[f["lang"]]
    label = submit if index == len(pages) - 1 else nxt
    popup = POPUP if f["popup"] else ""
    return (
        f'<!doctype html><html lang="{f["lang"]}"><meta charset="utf-8"><title>{html.escape(f["title"])}</title>'
        f"<body><h1>{html.escape(f['title'])}</h1>"
        f'<form method="post" action="/{f["id"]}/{index}">{fields}<button type="submit">{label}</button></form>{popup}</body></html>'
    )


class Server:
    """Hosts the forms on localhost and keeps what each form received."""

    def __init__(self):
        self.received = {}
        self.submitted = set()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body, status=200):
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parts = self.path.strip("/").split("/")
                f = BY_ID.get(parts[0])
                if f is None:
                    return self._send("not found", 404)
                index = int(parts[1]) if len(parts) > 1 else 0
                self._send(_page_html(f, index))

            def do_POST(self):
                _, form_id, index = self.path.split("/")
                f, index = BY_ID[form_id], int(index)
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                owner.received.setdefault(form_id, {}).update(parse_qsl(body))
                if index + 1 < len(f["pages"]):
                    self.send_response(303)
                    self.send_header("Location", f"/{form_id}/{index + 1}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    owner.submitted.add(form_id)
                    self._send(
                        f"<!doctype html><html><meta charset='utf-8'><title>Received</title><body>"
                        f"<h1>Received: {html.escape(f['title'])}</h1>"
                        "<p>Thank you. Your form has been received and no further action is needed.</p>"
                        "<a href='/'>Home</a></body></html>"
                    )

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        Thread(target=self.httpd.serve_forever, daemon=True).start()

    def score(self, f):
        """Per-field correctness of what the form received."""
        got = self.received.get(f["id"], {})
        want = gold(f)
        wrong = {k: got.get(k) for k, v in want.items() if got.get(k) != v}
        extra = {k: v for k, v in got.items() if k not in want and v}
        return {"submitted": f["id"] in self.submitted, "fields": len(want), "wrong": wrong, "extra": extra}


if __name__ == "__main__":
    print(json.dumps({f["id"]: gold(f) for f in FORMS}, ensure_ascii=False, indent=1)[:400])
