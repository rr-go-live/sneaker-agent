from langchain_google_genai import ChatGoogleGenerativeAI

# Gemini Flash is fast and cheap — appropriate for the short, structured
# prompts used across all agents. temperature=0 gives consistent output.
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)
