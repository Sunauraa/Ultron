"""Write the test persona's resume.pdf (a fictional person; every project and company is made up).

Usage: python bench/persona/make_resume.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

RESUME = [
    ("h1", "Mai Tran"),
    ("p", "San Francisco, CA · (415) 555-0142 · mai.tran@example.com · linkedin.com/in/mai-tran-dev · github.com/maitran-dev"),
    ("h2", "Experience"),
    ("b", "Senior Software Engineer, Brightline Analytics, San Francisco (March 2022 – present)"),
    ("li", "Lead the ingestion platform that loads 4 billion events a day from Kafka into PostgreSQL and S3 (Python, Go)."),
    ("li", "Built an internal tool that drafts SQL from plain-English questions with an LLM; 300 weekly users across sales and support."),
    ("li", "Cut the nightly batch from 6 hours to 50 minutes by moving it to incremental loads."),
    ("b", "Software Engineer, Northwind Logistics, Oakland (July 2019 – February 2022)"),
    ("li", "Wrote the shipment-tracking API (Go, gRPC) used by 40 partner carriers."),
    ("li", "Built integrations with carrier systems over REST, SFTP and EDI, with retries and alerting."),
    ("h2", "Open source"),
    ("li", "Author and maintainer of tidewater (github.com/maitran-dev/tidewater), a small Python library for retrying flaky HTTP calls."),
    ("h2", "Education"),
    ("b", "University of California, Berkeley: B.S. in Computer Science, 2019"),
    ("h2", "Skills"),
    ("p", "Python, Go, SQL, PostgreSQL, Kafka, AWS (S3, Lambda, ECS), Docker, Terraform, LLM APIs. Remote and hybrid teams since 2020."),
    ("p", "Languages: English (native), Vietnamese (fluent)."),
]


def main() -> None:
    styles = getSampleStyleSheet()
    look = {"h1": styles["Title"], "h2": styles["Heading2"], "b": styles["Heading4"], "p": styles["BodyText"], "li": styles["BodyText"]}
    story = []
    for kind, text in RESUME:
        story.append(Paragraph(("• " if kind == "li" else "") + text, look[kind]))
        if kind == "h1":
            story.append(Spacer(1, 4))
    SimpleDocTemplate(str(Path(__file__).with_name("resume.pdf")), pagesize=letter, title="Mai Tran resume").build(story)


if __name__ == "__main__":
    main()
