.PHONY: init test lint pretty precommit_install bump_major bump_minor bump_patch docs

# if BIN not provided, try to detect the binary from the environment
PYTHON_INSTALL := $(shell python3 -c 'import sys;print(sys.executable)')
BIN ?= $(shell [ -e .venv/bin ] && echo `pwd`/'.venv/bin' || dirname $(PYTHON_INSTALL))/

CODE = source_query_proxy

help:  ## This help dialog.
	@IFS=$$'\n' ; \
	help_lines=(`fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##/:/'`); \
	printf "%-15s %s\n" "target" "help" ; \
	printf "%-15s %s\n" "------" "----" ; \
	for help_line in $${help_lines[@]}; do \
		IFS=$$':' ; \
		help_split=($$help_line) ; \
		help_command=`echo $${help_split[0]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		help_info=`echo $${help_split[2]} | sed -e 's/^ *//' -e 's/ *$$//'` ; \
		printf '\033[36m'; \
		printf "%-15s %s" $$help_command ; \
		printf '\033[0m'; \
		printf "%s\n" $$help_info; \
	done


init:
	python3 -m venv .venv
	poetry install

test:   ## Запуск тестов
	$(BIN)python -m pytest --cov=$(CODE) $(args)

lint:  ## Проверка кода (linting)
	$(BIN)flake8 --jobs 4 --statistics --show-source $(CODE) tests
	$(BIN)black --target-version=py38 --skip-string-normalization --line-length=120 --check $(CODE) tests
	#$(BIN)python -m pytest --dead-fixtures --dup-fixtures  # disabled due _old_style_conf_d_globals detected as unused

pretty:  ## Автоформатирование согласно code-style
	$(BIN)isort $(CODE) tests
	$(BIN)black --target-version=py38 --skip-string-normalization --line-length=120 $(CODE) tests
	$(BIN)unify --in-place --recursive $(CODE) tests

precommit_install:  ## Установка pre-commit хука с проверками code-style и мелкими авто-справлениеями
	echo '#!/bin/sh' >  .git/hooks/pre-commit
	echo "exec make lint test BIN=$(BIN)" >> .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit

bump_major:
	$(BIN)bumpversion major
	$(BIN)python3 update_setup.py
	git add setup.py
	git commit --amend --no-edit

bump_minor:
	$(BIN)bumpversion minor
	$(BIN)python3 update_setup.py
	git add setup.py
	git commit --amend --no-edit

bump_patch:
	$(BIN)bumpversion patch
	$(BIN)python3 update_setup.py
	git add setup.py
	git commit --amend --no-edit


publish:
	git push origin master --tags
