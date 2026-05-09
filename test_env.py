import os
from dotenv import load_dotenv
load_dotenv()
print("MOCK_MONITORING:", os.environ.get('MOCK_MONITORING'))
