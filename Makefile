.PHONY: install bootstrap verify render-config update component-status

install:
	./scripts/bootstrap

bootstrap: install

verify:
	./scripts/verify

render-config:
	./scripts/render-config

update:
	./scripts/update

component-status:
	./scripts/component-status
