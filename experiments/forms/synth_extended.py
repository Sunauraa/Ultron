"""Extended training data for cua-s1-forms: wider English labels, Vietnamese, generic labels.

Wraps cua_s1.synth without changing it, swapping its vocabulary per episode. The exact document
labels used by data/forms/real/testset.json are kept out of training document labels.

Usage: synth_extended.py OUT_DIR EPISODES [SEED]
"""

import json
import random
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "third_party/cua/libs/cua-s1/python/src"))

from cua_s1 import synth  # noqa: E402
from cua_s1.concepts import Concept  # noqa: E402

EN_FORM_EXTRA = {
    "full_name": ("Name", "Your name", "Applicant name", "Full legal name", "Customer name", "Contact name"),
    "first_name": ("Forename", "Given name"),
    "last_name": ("Surname", "Family name"),
    "phone": ("Telephone", "Telephone number", "Tel", "Mobile", "Cell phone", "Contact number", "Phone / Cell"),
    "email": ("E-mail", "E-mail address", "Your email", "Contact email"),
    "dob": ("Birth date", "Date of Birth (mm/dd/yyyy)", "Born"),
    "street": ("Address", "Address 1", "Address1", "Home address", "Current address", "Street name", "Residence"),
    "city": ("What town do you live in?", "Municipality"),
    "zip": ("Zip", "Post code", "Postal code", "Postcode"),
}
EN_DOC_EXTRA = {
    "full_name": ("Full legal name", "Customer", "Client name"),
    "phone": ("Telephone", "Tel", "Cell"),
    "email": ("Email", "Mail"),
    "street": ("Address", "Home", "Mailing address"),
    "zip": ("ZIP", "Post code"),
}

VI_LAST = ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý")
VI_MID = ("Văn", "Thị", "Hữu", "Minh", "Đức", "Thanh", "Ngọc", "Quốc", "Hoài", "Gia")
VI_FIRST = ("An", "Bình", "Chi", "Dũng", "Giang", "Hải", "Hương", "Khánh", "Linh", "Mai", "Nam", "Phúc", "Quân", "Sơn", "Trang", "Tuấn", "Yến")
VI_STREET = ("Lê Lợi", "Nguyễn Huệ", "Hai Bà Trưng", "Điện Biên Phủ", "Lý Thường Kiệt", "Hùng Vương", "Quang Trung", "Phan Chu Trinh")
VI_CITY = ("Hà Nội", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Huế", "Nha Trang", "Vinh", "Biên Hòa", "TP. Hồ Chí Minh")
VI_DISTRICT = ("Quận 1", "Cầu Giấy", "Hải Châu", "Ninh Kiều", "Đống Đa", "Thanh Khê", "Bình Thạnh")
VI_COMPANY = ("Công ty TNHH An Phát", "Công ty CP Sao Mai", "Tập đoàn Hòa Bình", "Công ty TNHH Thành Đạt", "Ngân hàng Á Châu")
VI_SCHOOL = ("Đại học Bách khoa Hà Nội", "Trường THPT Lê Quý Đôn", "Đại học Kinh tế TP.HCM", "Trường THPT Nguyễn Trãi", "Đại học Cần Thơ")
VI_JOB = ("Kế toán", "Kỹ sư phần mềm", "Giáo viên", "Nhân viên kinh doanh", "Điều dưỡng", "Trưởng phòng")


def digits(r, n):
    return "".join(r.choice("0123456789") for _ in range(n))


def vi_name(r):
    return f"{r.choice(VI_LAST)} {r.choice(VI_MID)} {r.choice(VI_FIRST)}"


def vi_phone(r):
    return r.choice(("09", "03", "07", "08")) + digits(r, 8)


def vi_date(r):
    return f"{r.randint(1, 28):02}/{r.randint(1, 12):02}/{r.randint(1960, 2010)}"


def vi_address(r):
    return f"{r.randint(1, 300)} {r.choice(VI_STREET)}, {r.choice(VI_DISTRICT)}"


def vi_email(r):
    return f"{r.choice(VI_FIRST).lower().replace('đ', 'd')}{digits(r, 3)}@example.com".encode("ascii", "ignore").decode()


# key: (form labels, document labels, group, value). The keys cua_s1.synth names as look-alike
# pairs are all present, because it looks them up directly.
VI_TABLE = {
    "full_name": (("Họ và tên", "Họ tên", "Tên đầy đủ", "Họ và tên thí sinh", "Tên khách hàng", "Họ tên học viên", "Tên"), ("Họ và tên", "Họ tên", "Khách hàng", "Người đăng ký"), "identity", lambda r, p: vi_name(r)),
    "first_name": (("Tên", "Tên gọi"), ("Tên", "Tên gọi"), "identity", lambda r, p: r.choice(VI_FIRST)),
    "last_name": (("Họ",), ("Họ", "Họ của bạn"), "identity", lambda r, p: r.choice(VI_LAST)),
    "dob": (("Ngày sinh", "Ngày tháng năm sinh", "Ngày, tháng, năm sinh", "Sinh ngày"), ("Ngày sinh", "Ngày tháng năm sinh"), "identity", lambda r, p: vi_date(r)),
    "id_number": (("Số CCCD", "Số CMND/CCCD", "CMND - CCCD", "Căn cước công dân", "Số căn cước", "Số chứng minh nhân dân"), ("CCCD", "Số CCCD", "CMND", "Số định danh"), "identity", lambda r, p: digits(r, 12)),
    "gender": (("Giới tính",), ("Giới tính",), "identity", lambda r, p: r.choice(("Nam", "Nữ"))),
    "phone": (("Số điện thoại", "Điện thoại", "Điện thoại liên hệ", "SĐT", "Di động", "Số điện thoại di động", "Tel"), ("Số điện thoại", "Điện thoại", "SĐT", "ĐT"), "contact", lambda r, p: vi_phone(r)),
    "work_phone": (("Điện thoại cơ quan", "Số điện thoại công ty"), ("Điện thoại cơ quan",), "work", lambda r, p: "028" + digits(r, 8)),
    "email": (("Email", "E-mail", "Địa chỉ email", "Thư điện tử", "Email thường dùng", "Hòm thư"), ("Email", "E-mail", "Thư điện tử", "Địa chỉ email"), "contact", lambda r, p: vi_email(r)),
    "street": (("Địa chỉ", "Địa chỉ liên hệ", "Địa chỉ hiện tại", "Địa chỉ thường trú", "Địa chỉ cụ thể", "Nơi ở", "Nơi ở hiện nay"), ("Địa chỉ", "Địa chỉ thường trú", "Chỗ ở hiện tại"), "address", lambda r, p: vi_address(r)),
    "city": (("Thành phố", "Tỉnh/Thành phố", "Tỉnh thành"), ("Thành phố", "Tỉnh"), "address", lambda r, p: r.choice(VI_CITY)),
    "state": (("Quận/Huyện", "Huyện", "Quận"), ("Quận", "Huyện"), "address", lambda r, p: r.choice(VI_DISTRICT)),
    "zip": (("Mã bưu chính", "Mã bưu điện"), ("Mã bưu chính",), "address", lambda r, p: digits(r, 6)),
    "country": (("Quốc gia", "Quốc tịch"), ("Quốc tịch", "Quốc gia"), "address", lambda r, p: "Việt Nam"),
    "employer": (("Tên công ty", "Công ty", "Cơ quan công tác", "Đơn vị công tác", "Nơi làm việc"), ("Công ty", "Cơ quan", "Đơn vị"), "work", lambda r, p: r.choice(VI_COMPANY)),
    "job_title": (("Chức vụ", "Chức danh", "Nghề nghiệp"), ("Chức vụ", "Nghề nghiệp"), "work", lambda r, p: r.choice(VI_JOB)),
    "start_date": (("Ngày bắt đầu", "Ngày vào làm"), ("Ngày bắt đầu",), "work", lambda r, p: vi_date(r)),
    "university": (("Trường", "Tên trường", "Trường học", "Trường THPT", "Trường đại học", "Nơi học"), ("Trường", "Trường học", "Tốt nghiệp trường"), "education", lambda r, p: r.choice(VI_SCHOOL)),
    "ec_name": (("Họ tên người thân", "Người liên hệ khẩn cấp", "Họ và tên phụ huynh", "Họ và tên cha/mẹ"), ("Người thân", "Phụ huynh"), "emergency", lambda r, p: vi_name(r)),
    "ec_phone": (("Điện thoại người thân", "Số điện thoại phụ huynh", "Số điện thoại cha/mẹ"), ("SĐT người thân", "SĐT phụ huynh"), "emergency", lambda r, p: vi_phone(r)),
    "incident_date": (("Ngày xảy ra sự việc", "Ngày khám"), ("Ngày khám",), "insurance", lambda r, p: vi_date(r)),
    "insurer": (("Công ty bảo hiểm", "Đơn vị bảo hiểm"), ("Nhà bảo hiểm",), "insurance", lambda r, p: r.choice(("Bảo Việt", "PVI", "Bảo Minh"))),
    "policy": (("Số hợp đồng bảo hiểm", "Mã thẻ bảo hiểm", "Mã số thẻ BHYT"), ("Số thẻ BHYT", "Mã BHYT"), "insurance", lambda r, p: "DN" + digits(r, 13)),
    "account": (("Số tài khoản", "Số tài khoản ngân hàng"), ("Số tài khoản", "STK"), "finance", lambda r, p: digits(r, 12)),
    "tax": (("Mã số thuế", "MST"), ("Mã số thuế", "MST"), "finance", lambda r, p: digits(r, 10)),
}
VI_LISTS = {
    "OPTIONAL_FIELDS": ("Mã giới thiệu", "Ghi chú", "Lời nhắn", "Nội dung", "Bạn biết đến chúng tôi qua đâu?", "Số fax", "Mã khuyến mãi", "Câu hỏi của bạn", "Link Facebook", "Chiều cao", "Cân nặng", "Khóa học muốn tham gia", "Mô tả triệu chứng", "Ý kiến khác", "Nơi sinh", "Quê quán"),
    "SUBMIT_LABELS": ("Gửi", "Gửi đi", "Đăng ký", "Đăng ký ngay", "Tiếp theo", "Tiếp tục", "Hoàn tất", "Xác nhận", "Nộp hồ sơ", "Gửi thông tin", "Đặt lịch", "Lưu và tiếp tục"),
    "NON_SUBMIT_BUTTONS": ("Hủy", "Hủy bỏ", "Xóa", "Xóa biểu mẫu", "Quay lại", "Trở về", "Đóng", "Đặt lại", "Trợ giúp", "Đăng xuất", "In", "Tải tệp lên"),
    "REQUIRED_CHECKBOXES": ("Tôi đồng ý với các điều khoản", "Tôi đồng ý với chính sách bảo mật", "Tôi xác nhận thông tin trên là đúng", "Tôi cam đoan thông tin là chính xác", "Tôi đã đọc và chấp nhận điều khoản sử dụng"),
    "OPTIONAL_CHECKBOXES": ("Nhận bản tin qua email", "Đăng ký nhận khuyến mãi", "Nhắc lịch qua tin nhắn", "Ghi nhớ đăng nhập", "Nhận thông tin ưu đãi"),
    "FORM_TITLES": ("Phiếu đăng ký", "Đăng ký tư vấn", "Đặt lịch khám", "Đăng ký khóa học", "Liên hệ", "Hồ sơ ứng tuyển", "Đăng ký xét tuyển", "Thông tin khách hàng", "Đăng ký tìm việc", "Biểu mẫu", "Mẫu đăng ký"),
}
VI_DISTRACTORS = (
    ("Mã hồ sơ", lambda r: "HS-" + digits(r, 6)),
    ("Ngày in", lambda r: vi_date(r)),
    ("Trang", lambda r: f"1/{r.randint(1, 4)}"),
    ("Người lập", vi_name),
    ("Số fax", lambda r: "028" + digits(r, 8)),
    ("Chiều cao", lambda r: f"{r.randint(150, 190)} cm"),
    ("Cân nặng", lambda r: f"{r.randint(45, 95)} kg"),
    ("Tham chiếu", lambda r: digits(r, 8)),
)

# Labels with no fixed meaning, matched only by copying: form and document share the wording.
GENERIC_EN = (
    "Project code", "Membership tier", "Department", "Team", "Building", "Room number", "Season", "Warehouse", "Region code", "Batch number",
    "Course title", "Supervisor", "Mentor", "Branch office", "Sponsor", "Parcel weight", "License plate", "Meter reading", "Contract type", "Order reference",
    "Delivery window", "Case number", "Ticket number", "Grant name", "Program name", "Clinic", "Ward", "Pharmacy", "Store number", "Route",
    "Crew", "Shift", "Vessel", "Trailer", "Tenant", "Landlord", "Unit price", "Quantity", "Total cost", "Budget",
    "Topic", "Headline", "Reason for visit", "Purpose of travel", "Destination", "Origin", "Asset tag", "Serial number", "Model name", "Product line",
)
GENERIC_VI = (
    "Phòng ban", "Bộ phận", "Mã dự án", "Tòa nhà", "Số phòng", "Kho hàng", "Mã khu vực", "Số lô", "Tên khóa học", "Người hướng dẫn",
    "Chi nhánh", "Biển số xe", "Loại hợp đồng", "Mã đơn hàng", "Số hồ sơ", "Tên chương trình", "Phòng khám", "Nhà thuốc", "Mã cửa hàng", "Tuyến đường",
    "Ca làm việc", "Đơn giá", "Số lượng", "Tổng chi phí", "Ngân sách", "Chủ đề", "Lý do khám", "Mục đích chuyến đi", "Điểm đến", "Mã tài sản",
    "Số sê-ri", "Tên sản phẩm", "Ngành học", "Lớp", "Niên khóa", "Bằng cấp", "Xếp loại", "Khoa", "Học phí", "Hình thức thanh toán",
)


def generic_value(r):
    return r.choice((digits(r, 5), f"{r.choice('ABCDEFGHKLMN')}{digits(r, 3)}", r.choice(("Standard", "Gold", "North", "Alpha", "Loại A", "Đợt 2", "Khu B", "Sáng"))))


def decorate(labels, lang):
    """Add the label decorations real forms use: required marks, colons, numbering, prompts."""
    out = list(labels)
    for label in labels:
        out += [f"{label} *", f"{label}:", label.upper(), f"* {label}"]
        out += [f"1. {label}", f"4. {label}"]
        out.append(f"Nhập {label[0].lower()}{label[1:]}" if lang == "vi" else f"Enter {label[0].lower()}{label[1:]}")
    return tuple(dict.fromkeys(out))


def test_doc_labels():
    data = json.loads((ROOT / "data/forms/real/testset.json").read_text())
    return {entry[0] for document in data["documents"].values() for entry in document.values()}


def build_vocabularies():
    held_out = test_doc_labels()
    base = synth.CONCEPTS

    def concept(key, form, doc, value, group, lang):
        doc = tuple(d for d in doc if d not in held_out) or (form[0],)
        return Concept(key, decorate(form, lang), doc, value, group=group)

    en = []
    for c in base:
        doc = tuple(d for d in c.doc_labels + EN_DOC_EXTRA.get(c.key, ()) if d not in held_out) or c.doc_labels
        en.append(replace(c, form_labels=decorate(c.form_labels + EN_FORM_EXTRA.get(c.key, ()), "en"), doc_labels=doc))
    for label in GENERIC_EN:
        en.append(concept("g_" + label, (label,), (label,), lambda r, p: generic_value(r), "generic", "en"))

    vi = [concept(k, form, doc, value, group, "vi") for k, (form, doc, group, value) in VI_TABLE.items()]
    for label in GENERIC_VI:
        vi.append(concept("g_" + label, (label,), (label,), lambda r, p: generic_value(r), "generic", "vi"))

    original = {name: getattr(synth, name) for name in (*VI_LISTS, "DISTRACTOR_ENTITIES")}
    filtered = [
        replace(c, doc_labels=tuple(d for d in c.doc_labels if d not in held_out) or c.doc_labels) for c in base
    ]
    original.update(CONCEPTS=filtered, CONCEPT_BY_KEY={c.key: c for c in filtered})
    vi_vocab = {**VI_LISTS, "DISTRACTOR_ENTITIES": VI_DISTRACTORS, "CONCEPTS": vi, "CONCEPT_BY_KEY": {c.key: c for c in vi}}
    en_vocab = {**original, "CONCEPTS": en, "CONCEPT_BY_KEY": {c.key: c for c in en}}
    return original, en_vocab, vi_vocab


def main():
    out, episodes = sys.argv[1], int(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    original, en_vocab, vi_vocab = build_vocabularies()
    rows = synth.episode_rows

    def mixed(episode_seed, config=None):
        pick = random.Random(episode_seed ^ 0x5eed).random()
        vocab = original if pick < 0.2 else en_vocab if pick < 0.5 else vi_vocab
        for name, value in vocab.items():
            setattr(synth, name, value)
        return rows(episode_seed, config)

    synth.episode_rows = mixed
    print(json.dumps(synth.write_splits(out, episodes, seed), ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
