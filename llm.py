from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables from a local .env file before constructing the
# client. This must run before ChatGoogleGenerativeAI() so GOOGLE_API_KEY is
# present in the environment. override=True makes the .env file authoritative
# even if a stale GOOGLE_API_KEY is already exported in the shell that launched
# the server — without it, an old exported key would silently win over the
# correct value in .env. .env is gitignored, so it never reaches a deployment
# where platform-injected env vars should take precedence.
load_dotenv(override=True)

# Gemini Flash is fast and cheap — appropriate for the short, structured
# prompts used across all agents. temperature=0 gives consistent output.
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)
