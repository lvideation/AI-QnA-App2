# sanity_check.py
import streamlit, openai, pandas, numpy, langchain
from faker import Faker
import importlib.metadata

print("✅ Streamlit:", streamlit.__version__)
print("✅ OpenAI:", openai.__version__)
print("✅ Pandas:", pandas.__version__)
print("✅ Numpy:", numpy.__version__)
print("✅ Faker:", importlib.metadata.version("faker"))
print("✅ LangChain:", langchain.__version__)
print("✅ Ollama:", importlib.metadata.version("ollama"))
