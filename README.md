# notebooklm-automation

Batch prompt runner for NotebookLM study workflows.

notebooklm login --storage "$env:NOTEBOOKLM_HOME\storage_state.json"

Notebooklm-py file was modified to increase timeout ceiling:
1. Go to your virtual environment
2. then find Lib/site-packages/notebooklm/_core.py
  - Edit the timeout to match this
  ```
  timeout = httpx.Timeout(
                connect=10.0,
                read=None,
                write=120.0,
                pool=120.0,
            )
  ```


### For testing one concept
nlm-auto --limit-concepts 1 --limit-prompts 9 --overwrite 

### for all concepts
nlm-auto --overwrite 