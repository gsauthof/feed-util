.PHONY: srpm
srpm:
	dnf -y install git-core
	git archive --prefix feed-utils/ -o feed-utils.tar HEAD
	rpmbuild --define "_sourcedir $$PWD" --define "_specdir $$PWD" --define "_builddir $$PWD" --define "_rpmdir $(outdir)" --define "_srcrpmdir $(outdir)" -bs feed-utils.spec
