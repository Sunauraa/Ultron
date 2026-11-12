"""English and Vietnamese form episodes for retraining cua-s1-forms. Usage: synth_forms.py OUT EPISODES SEED

Vietnamese episodes reuse Cua's generator by swapping its vocabulary for the one below. Both languages
get the decorated labels real pages use (" *", ":", "Please enter ..."). The exact document wording of
data/forms/real/testset.json is left out of the vocabulary, so the model has to generalise to it.
"""

import dataclasses
import json
import os
import random
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))

from cua_s1 import concepts as en  # noqa: E402
from cua_s1 import synth  # noqa: E402
from cua_s1.concepts import C  # noqa: E402

HO = "Nguyễn Trần Lê Phạm Hoàng Huỳnh Phan Vũ Võ Đặng Bùi Đỗ Hồ Ngô Dương Lý".split()
DEM = "Văn Thị Hữu Đức Minh Thu Thanh Ngọc Quốc Xuân Hồng Gia Anh Kim".split()
TEN = "An Bình Châu Dũng Giang Hà Hải Hùng Hương Khoa Lan Linh Long Mai Nam Nga Phong Phúc Quân Sơn Tâm Thảo Trang Tuấn Việt Yến".split()
DUONG = ["Lê Lợi", "Trần Hưng Đạo", "Nguyễn Huệ", "Hai Bà Trưng", "Lý Thường Kiệt", "Pasteur", "Điện Biên Phủ", "Võ Thị Sáu", "Cầu Giấy", "Kim Mã", "Bạch Đằng", "Hùng Vương"]
TINH = ["Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Huế", "Nghệ An", "Thanh Hóa", "Bình Dương", "Đồng Nai", "Khánh Hòa", "Quảng Ninh"]
QUAN = ["Ba Đình", "Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Quận 1", "Quận 3", "Bình Thạnh", "Thủ Đức", "Hải Châu", "Ninh Kiều", "Lê Chân", "Tân Bình"]
PHUONG = ["Phường Bến Nghé", "Phường Dịch Vọng", "Phường Láng Hạ", "Phường 7", "Xã Tân Lập", "Phường Hải Châu 1", "Thị trấn Đông Anh"]
CONG_TY = ["Công ty TNHH Hòa Phát", "Công ty CP Sao Mai", "Công ty TNHH Thành Công", "Tập đoàn Việt Á", "Công ty CP Bình Minh", "Doanh nghiệp tư nhân Tân Tiến"]
TRUONG = ["Đại học Bách khoa Hà Nội", "Đại học Kinh tế TP.HCM", "Trường THPT Lê Hồng Phong", "Đại học Cần Thơ", "Trường THCS Nguyễn Du", "Học viện Tài chính", "Đại học Đà Nẵng"]
NGAN_HANG = ["Vietcombank", "BIDV", "VietinBank", "Techcombank", "MB Bank", "ACB", "Sacombank"]
BAO_HIEM = ["Bảo Việt", "PVI", "Bảo Minh", "Bảo hiểm Xã hội Việt Nam", "Prudential Việt Nam"]
CHUC_DANH = ["Kế toán", "Nhân viên kinh doanh", "Kỹ sư phần mềm", "Giáo viên", "Trưởng phòng", "Bác sĩ", "Lễ tân"]
QUAN_HE = ["Bố", "Mẹ", "Vợ", "Chồng", "Anh trai", "Chị gái", "Con"]


def digits(rng, n):
    return "".join(rng.choice("0123456789") for _ in range(n))


def phone(rng):
    return rng.choice(("09", "03", "07", "08")) + digits(rng, 8)


def date(rng, low=1960, high=2008):
    day, month, year = rng.randint(1, 28), rng.randint(1, 12), rng.randint(low, high)
    return rng.choice((f"{day:02}/{month:02}/{year}", f"{day}/{month}/{year}", f"{day:02}-{month:02}-{year}"))


def strip_marks(text):
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def person(rng):
    ho, dem, ten = rng.choice(HO), rng.choice(DEM), rng.choice(TEN)
    mail = strip_marks(f"{ten}.{ho}").lower() + rng.choice(("", str(rng.randint(1, 99))))
    return {
        "first": ten, "last": ho, "full": f"{ho} {dem} {ten}",
        "email": f"{mail}@{rng.choice(('example.invalid', 'mail.example.invalid'))}",
    }


def other_name(rng):
    return f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"


def v(values):
    return lambda rng, _: rng.choice(values)


def n(count):
    return lambda rng, _: digits(rng, count)


VI_CONCEPTS = [
    C("first_name", ("Tên", "Tên của bạn", "Tên gọi", "First name"), ("Tên", "Tên gọi"), lambda r, p: p["first"], group="name"),
    C("last_name", ("Họ", "Họ của bạn", "Last name"), ("Họ", "Dòng họ"), lambda r, p: p["last"], group="name"),
    C("full_name", ("Họ và tên", "Họ tên", "Họ, tên", "Họ & tên", "Tên khách hàng", "Họ tên người đăng ký", "Họ và tên học viên", "Tên của bạn", "Họ tên học sinh", "Full name", "Tên đăng ký"),
      ("Họ và tên", "Họ tên", "Người đăng ký", "Khách hàng", "Tên người khai", "Học viên"), lambda r, p: p["full"], group="name"),
    C("email", ("Email", "E-mail", "Địa chỉ email", "Thư điện tử", "Địa chỉ thư điện tử", "Email của bạn", "Email liên hệ", "Gmail"),
      ("Email", "Địa chỉ email", "Thư điện tử", "Mail", "Hộp thư"), lambda r, p: p["email"], group="contact"),
    C("phone", ("Số điện thoại", "Điện thoại", "SĐT", "Số ĐT", "Điện thoại di động", "Số di động", "Điện thoại liên hệ", "SĐT liên hệ", "Số điện thoại của bạn", "Tel", "Zalo"),
      ("Điện thoại", "Số điện thoại", "SĐT", "Liên lạc", "Số liên hệ", "ĐT"), lambda r, p: phone(r), group="contact"),
    C("work_phone", ("Điện thoại cơ quan", "SĐT công ty", "Điện thoại nơi làm việc", "Điện thoại bàn"), ("Điện thoại cơ quan", "Máy bàn công ty"), lambda r, p: phone(r), group="contact"),
    C("dob", ("Ngày sinh", "Ngày tháng năm sinh", "Ngày, tháng, năm sinh", "Sinh nhật", "Năm sinh", "Ngày/tháng/năm sinh"), ("Ngày sinh", "Ngày tháng năm sinh", "Sinh nhật", "NS"), lambda r, p: date(r), group="date"),
    C("start_date", ("Ngày bắt đầu", "Ngày vào làm", "Ngày nhận việc", "Có thể bắt đầu từ ngày"), ("Ngày bắt đầu", "Ngày nhận việc"), lambda r, p: date(r, 2024, 2026), group="date"),
    C("incident_date", ("Ngày xảy ra sự cố", "Ngày tai nạn", "Ngày xảy ra"), ("Ngày sự cố", "Ngày tai nạn"), lambda r, p: date(r, 2024, 2026), group="date"),
    C("issue_date", ("Ngày cấp", "Ngày cấp CCCD", "Ngày cấp CMND"), ("Ngày cấp", "Cấp ngày"), lambda r, p: date(r, 2015, 2025), group="id"),
    C("issue_place", ("Nơi cấp", "Nơi cấp CCCD", "Nơi cấp CMND"), ("Nơi cấp", "Cấp tại"), lambda r, p: "Cục Cảnh sát QLHC về TTXH", group="id"),
    C("cccd", ("Số CCCD", "CCCD", "Số căn cước công dân", "Căn cước công dân", "CMND/CCCD", "Số CMND", "Chứng minh nhân dân", "Số chứng minh thư", "Số định danh cá nhân"),
      ("CCCD", "Số CCCD", "CMND/CCCD", "Số định danh", "Giấy tờ tùy thân"), n(12), group="id"),
    C("passport", ("Số hộ chiếu", "Hộ chiếu", "Passport"), ("Hộ chiếu", "Số hộ chiếu"), lambda r, p: "C" + digits(r, 7), group="id"),
    C("tax_id", ("Mã số thuế", "MST", "Mã số thuế cá nhân", "Mã số doanh nghiệp"), ("Mã số thuế", "MST", "Mã thuế"), n(10), group="id"),
    C("street", ("Địa chỉ", "Địa chỉ liên hệ", "Địa chỉ thường trú", "Địa chỉ nhà", "Địa chỉ hiện tại", "Số nhà, tên đường", "Địa chỉ của bạn", "Địa chỉ cư trú", "Địa chỉ nhận hàng"),
      ("Địa chỉ", "Thường trú", "Chỗ ở hiện tại", "Địa chỉ nhà", "Cư trú tại"), lambda r, p: f"{r.randint(1, 300)} {r.choice(DUONG)}, {r.choice(QUAN)}", group="address"),
    C("ward", ("Phường/Xã", "Phường", "Xã/Phường"), ("Phường/Xã", "Phường"), v(PHUONG), group="address"),
    C("district", ("Quận/Huyện", "Quận", "Huyện"), ("Quận/Huyện", "Quận"), v(QUAN), group="address"),
    C("city", ("Tỉnh/Thành phố", "Thành phố", "Tỉnh", "Tỉnh thành", "Tỉnh/TP", "Khu vực"), ("Tỉnh/Thành phố", "Thành phố", "Tỉnh"), v(TINH), group="address"),
    C("state", ("Vùng", "Miền"), ("Vùng", "Miền"), v(("Miền Bắc", "Miền Trung", "Miền Nam")), group="address"),
    C("zip", ("Mã bưu điện", "Mã bưu chính"), ("Mã bưu điện", "Bưu chính"), n(6), group="address"),
    C("country", ("Quốc gia", "Nước"), ("Quốc gia", "Nước"), v(("Việt Nam", "Nhật Bản", "Hàn Quốc", "Hoa Kỳ")), group="address"),
    C("nationality", ("Quốc tịch",), ("Quốc tịch",), v(("Việt Nam", "Nhật Bản", "Pháp")), group="address"),
    C("hometown", ("Quê quán", "Nguyên quán", "Nơi sinh"), ("Quê quán", "Nơi sinh"), v(TINH), group="address"),
    C("insurer", ("Công ty bảo hiểm", "Đơn vị bảo hiểm"), ("Bảo hiểm", "Công ty bảo hiểm"), v(BAO_HIEM), group="company"),
    C("policy", ("Số hợp đồng bảo hiểm", "Mã số BHXH", "Số thẻ BHYT"), ("Số hợp đồng", "Mã BHXH", "Thẻ BHYT"), n(10), group="finance"),
    C("employer", ("Công ty", "Tên công ty", "Đơn vị công tác", "Cơ quan", "Nơi công tác", "Tên doanh nghiệp", "Cơ quan công tác"), ("Công ty", "Đơn vị công tác", "Cơ quan", "Doanh nghiệp"), v(CONG_TY), group="company"),
    C("job_title", ("Chức vụ", "Chức danh", "Vị trí", "Nghề nghiệp", "Vị trí công việc"), ("Chức vụ", "Chức danh", "Nghề nghiệp"), v(CHUC_DANH), group="company"),
    C("university", ("Trường", "Tên trường", "Trường học", "Trường đại học", "Học tại trường", "Trường đang học"), ("Trường", "Trường học", "Đang học tại"), v(TRUONG), group="school"),
    C("class_name", ("Lớp", "Lớp học"), ("Lớp",), lambda r, p: f"{r.randint(6, 12)}A{r.randint(1, 9)}", group="school"),
    C("major", ("Ngành học", "Chuyên ngành"), ("Ngành", "Chuyên ngành"), v(("Kế toán", "Công nghệ thông tin", "Marketing", "Luật")), group="school"),
    C("bank", ("Ngân hàng", "Tên ngân hàng"), ("Ngân hàng",), v(NGAN_HANG), group="finance"),
    C("account", ("Số tài khoản", "STK", "Số tài khoản ngân hàng"), ("Số tài khoản", "STK", "Tài khoản"), n(12), group="finance"),
    C("ec_name", ("Họ tên phụ huynh", "Họ tên người thân", "Người liên hệ khẩn cấp", "Tên bố/mẹ", "Họ tên người giới thiệu", "Họ tên người nhận"), ("Phụ huynh", "Người thân", "Người giới thiệu"), lambda r, p: other_name(r), group="other"),
    C("ec_phone", ("SĐT phụ huynh", "Số điện thoại người thân", "Điện thoại người giới thiệu", "SĐT người nhận"), ("SĐT phụ huynh", "SĐT người thân"), lambda r, p: phone(r), group="other"),
    C("ec_relation", ("Quan hệ với người đăng ký", "Mối quan hệ"), ("Quan hệ",), v(QUAN_HE), group="other"),
    C("sex", ("Giới tính",), ("Giới tính",), v(("Nam", "Nữ")), group="personal"),
    C("marital", ("Tình trạng hôn nhân",), ("Hôn nhân",), v(("Độc thân", "Đã kết hôn")), group="personal"),
    C("ethnic", ("Dân tộc",), ("Dân tộc",), v(("Kinh", "Tày", "Thái", "Mường")), group="personal"),
    C("facebook", ("Facebook", "Link Facebook", "Trang cá nhân", "Website"), ("Facebook", "Website"), lambda r, p: "https://example.invalid/" + digits(r, 6), group="personal"),
    C("reason", ("Lý do", "Nội dung", "Nội dung cần tư vấn", "Yêu cầu của bạn", "Ghi chú", "Lời nhắn"), ("Lý do", "Nội dung", "Yêu cầu"), v(("Cần tư vấn thêm", "Đăng ký học thử", "Hỏi về học phí")), group="personal"),
]
OPTIONAL_FIELDS = (
    "Mã giới thiệu", "Mã khuyến mãi", "Mã giảm giá", "Bạn biết đến chúng tôi qua đâu?", "Ghi chú thêm (không bắt buộc)", "Câu hỏi khác", "Số fax", "Tên đệm",
    "Email phụ", "Mã nhân viên", "Mã xác nhận", "Nhập mã captcha", "Tìm kiếm", "Mã bảo mật", "Nguyện vọng khác",
)
SUBMIT_LABELS = ("Gửi", "Gửi đi", "Gửi thông tin", "Đăng ký", "Đăng ký ngay", "Tiếp theo", "Tiếp tục", "Hoàn tất", "Xác nhận", "Nộp hồ sơ", "Gửi đăng ký", "Lưu và tiếp tục", "Hoàn thành", "Đăng ký tư vấn", "Gửi yêu cầu", "Submit", "Tạo tài khoản")
NON_SUBMIT_BUTTONS = ("Hủy", "Hủy bỏ", "Đặt lại", "Xóa", "Xóa hết", "Quay lại", "Trở về", "Trang trước", "Đăng xuất", "Trợ giúp", "In mẫu", "Tải tệp lên", "Thêm dòng", "Đóng", "Thoát", "Làm lại")
REQUIRED_CHECKBOXES = (
    "Tôi đồng ý với các điều khoản", "Tôi đồng ý với điều khoản sử dụng", "Tôi xác nhận thông tin trên là đúng", "Tôi cam đoan các thông tin trên là chính xác",
    "Tôi đồng ý cho xử lý dữ liệu cá nhân", "Đồng ý với chính sách bảo mật", "Tôi đã đọc và đồng ý", "Xác nhận thông tin chính xác",
)
OPTIONAL_CHECKBOXES = ("Nhận bản tin qua email", "Đăng ký nhận khuyến mãi", "Nhận tin nhắn quảng cáo", "Chia sẻ dữ liệu với đối tác", "Ghi nhớ tôi", "Tham gia chương trình khách hàng thân thiết", "Nhận thông báo qua SMS")
FORM_TITLES = (
    "Đăng ký khám bệnh", "Đơn xin việc", "Đăng ký tuyển sinh", "Phiếu đăng ký học", "Đăng ký tư vấn", "Hồ sơ khách hàng", "Mở tài khoản ngân hàng", "Đăng ký thành viên",
    "Tờ khai thông tin", "Phiếu yêu cầu dịch vụ", "Đăng ký dự thi", "Liên hệ với chúng tôi", "Đăng ký nhân viên mới", "Đăng ký doanh nghiệp",
)
DISTRACTOR_ENTITIES = (
    ("Mã hồ sơ", lambda r: "HS-" + digits(r, 6)),
    ("Ngày in", lambda r: date(r, 2026, 2026)),
    ("Trang", lambda r: f"1/{r.randint(1, 4)}"),
    ("Người lập", other_name),
    ("Chiều cao", lambda r: f"{r.randint(150, 185)} cm"),
    ("Cán bộ tiếp nhận", other_name),
)


# Wording of the real-form documents, kept out of training in every language.
HELD_OUT = {
    "Applicant", "Given name", "Family name", "Born", "Contact number", "E-mail address", "Residence", "Municipality", "Province or state", "Postcode",
    "Tên đầy đủ", "Sinh ngày", "Căn cước", "Di động", "Hòm thư", "Nơi ở", "Nơi học", "Nơi làm việc",
}


EN_WORDS = ("Billing Work Home Second Primary Project Delivery Order Invoice Ticket Customer Vendor Owner Recipient Sender Contract Payment Event Student Branch Office Team Case Product Service Business Reference Contact Shipping Client "
            "Manager Supplier Parent Warehouse Region Department").split()
EN_NOUNS = ("name subject code number email phone address notes title date amount category topic message type status city ID label comment summary manager account location description").split()
VI_WORDS = ("công việc nhà riêng dự án giao hàng đơn hàng hóa đơn khách hàng đối tác chủ sở hữu người nhận người gửi hợp đồng thanh toán sự kiện học viên chi nhánh văn phòng sản phẩm dịch vụ doanh nghiệp tham chiếu liên hệ "
            "phòng ban nhà cung cấp khu vực").split()
VI_NOUNS = ("Tên Mã Số Email Điện thoại Địa chỉ Ghi chú Tiêu đề Ngày Số tiền Loại Chủ đề Nội dung Trạng thái Thông tin Mô tả").split(" ")


OPEN_GROUPS = int(os.environ.get("OPEN_GROUPS", "5"))


def open_concepts(words, nouns, vietnamese):
    """Field names outside the catalogue. A label shared by form and document means fill, whatever the words are."""
    rng = random.Random(11)
    concepts = []
    for number in range(600):
        word, noun = rng.choice(words), rng.choice(nouns)
        label = f"{noun} {word}" if vietnamese else f"{word} {noun}"
        if rng.random() < 0.15:
            label = rng.choice(nouns if vietnamese else words)
        value = rng.choice((lambda r, _: digits(r, r.randint(4, 12)), lambda r, _: "-".join((r.choice(("AB", "XK", "TN", "MS")), digits(r, 5))), lambda r, _: " ".join(r.sample(words, 2)).capitalize()))
        concepts.append(C(f"open{number}", (label, label), (label, label), value, group=f"open{number % OPEN_GROUPS}"))
    return concepts


def wrap(concept, starts, ends, generic):
    """Decorate form labels and widen document labels, so wording and value shape both have to be read."""
    labels = list(concept.form_labels)
    for label in concept.form_labels:
        labels += [f"{label}{end}" for end in ends] + [f"{start}{label}" for start in starts] + [label.upper()]
    documents = [x for x in (*concept.doc_labels, *concept.doc_labels, *concept.form_labels) if x not in HELD_OUT]
    documents += generic[: max(1, len(documents) // 16)]
    return dataclasses.replace(concept, form_labels=tuple(labels), doc_labels=tuple(documents))


VI_STARTS = ("Nhập ", "Vui lòng nhập ", "Điền ", "Ghi ", "1. ", "6. ", "12. ", "* ")
EN_STARTS = ("Enter your ", "Please enter your ", "Your ", "Current ", "1. ", "6. ", "* ")
VI_GENERIC = ("Thông tin", "Mục 3", "Dữ liệu", "Chi tiết", "Khác")
EN_GENERIC = ("Info", "Item 3", "Details", "Data", "Other")
ENDS = (" *", ":", " :", " (*)", " (bắt buộc)", " *:", " của bạn", " của Anh/Chị", " của Anh/Chị :", " thí sinh", " cụ thể", " thường xuyên sử dụng")
EN_ENDS = (" *", ":", " :", " (*)", " (required)", " *:")


def install(language):
    """Point Cua's generator at one language's vocabulary."""
    if language == "vi":
        concepts = [wrap(c, VI_STARTS, ENDS, VI_GENERIC) for c in VI_CONCEPTS + open_concepts(VI_WORDS, VI_NOUNS, True)]
        names = dict(OPTIONAL_FIELDS=OPTIONAL_FIELDS, SUBMIT_LABELS=SUBMIT_LABELS, NON_SUBMIT_BUTTONS=NON_SUBMIT_BUTTONS, REQUIRED_CHECKBOXES=REQUIRED_CHECKBOXES,
                     OPTIONAL_CHECKBOXES=OPTIONAL_CHECKBOXES, FORM_TITLES=FORM_TITLES, DISTRACTOR_ENTITIES=DISTRACTOR_ENTITIES, person=person)
    else:
        concepts = [wrap(c, EN_STARTS, EN_ENDS, EN_GENERIC) for c in list(en.CONCEPTS) + open_concepts(EN_WORDS, EN_NOUNS, False)]
        names = dict(OPTIONAL_FIELDS=en.OPTIONAL_FIELDS, SUBMIT_LABELS=en.SUBMIT_LABELS, NON_SUBMIT_BUTTONS=en.NON_SUBMIT_BUTTONS, REQUIRED_CHECKBOXES=en.REQUIRED_CHECKBOXES,
                     OPTIONAL_CHECKBOXES=en.OPTIONAL_CHECKBOXES, FORM_TITLES=en.FORM_TITLES, DISTRACTOR_ENTITIES=en.DISTRACTOR_ENTITIES, person=en.person)
    synth.CONCEPTS = concepts
    synth.CONCEPT_BY_KEY = {c.key: c for c in concepts}
    for name, value in names.items():
        setattr(synth, name, value)


def main():
    out, episodes, seed = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    handles = {s: (out / f"{s}.jsonl").open("w") for s in synth.SPLIT_NAMES}
    counts = {s: 0 for s in synth.SPLIT_NAMES}
    for index in range(episodes):
        language = "vi" if index % 2 else "en"
        install(language)
        rows = synth.episode_rows(seed + index * 7919)
        if language == "vi" and random.Random(seed + index).random() < 0.1:
            for row in rows:  # some people and forms type Vietnamese without marks
                row["context"], row["options"] = strip_marks(row["context"]), [strip_marks(o) for o in row["options"]]
        bucket = synth._stable_fraction(language + synth.signature(rows))
        split = "train" if bucket < 0.9 else "validation" if bucket < 0.95 else "test"
        for row in rows:
            row["meta"]["lang"] = language
            handles[split].write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        counts[split] += len(rows)
    print(counts)


if __name__ == "__main__":
    main()
