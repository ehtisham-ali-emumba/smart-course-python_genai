run:
	.venv/bin/uvicorn main:app --reload

learn:
	.venv/bin/python learn_and_debug.py

learn-watch:
	echo learn_and_debug.py | entr -c .venv/bin/python learn_and_debug.py
