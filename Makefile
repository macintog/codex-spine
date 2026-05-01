.PHONY: install bootstrap verify render-config update upgrade component-status

install:
	./scripts/bootstrap

bootstrap: install

verify:
	./scripts/verify

render-config:
	./scripts/render-config

update:
	./scripts/update

upgrade:
	./scripts/upgrade

component-status:
	./scripts/component-status
