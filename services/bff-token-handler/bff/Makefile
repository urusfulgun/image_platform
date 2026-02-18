include .env

clean-cache-files:
	python3 -Bc "for p in __import__('pathlib').Path('.').rglob('*.py[co]'): p.unlink()"
clean-cache-folders:
	python3 -Bc "for p in __import__('pathlib').Path('.').rglob('__pycache__'): p.rmdir()"
clean-cache: clean-cache-files clean-cache-folders

test:
	uv run --env-file=.env pytest
