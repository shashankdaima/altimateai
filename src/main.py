import sys
import fitz  # pymupdf
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv

load_dotenv()


def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def summarize_pdf(pdf_path: str) -> str:
    text = extract_text_from_pdf(pdf_path)

    llm = LLM(model="anthropic/claude-sonnet-4-6")

    summarizer = Agent(
        role="Document Summarizer",
        goal="Summarize PDF documents accurately and concisely",
        backstory="You are an expert at reading and summarizing documents.",
        llm=llm,
        verbose=True,
    )

    task = Task(
        description=f"Summarize the following document:\n\n{text}",
        expected_output="A clear and concise summary of the document.",
        agent=summarizer,
    )

    crew = Crew(agents=[summarizer], tasks=[task])
    result = crew.kickoff()
    return result.raw


if __name__ == "__main__":
    pdf_path =  "samples/TodoPRD.pdf"
    summary = summarize_pdf(pdf_path)
    print("\n--- SUMMARY ---\n")
    print(summary)
