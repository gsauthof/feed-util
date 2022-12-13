%bcond_without srpm


Name:       feed-utils
Version:    0.6.1
Release:    1%{?dist}
Summary:    Collection of RSS/Atom utilities
URL:        https://github.com/gsauthof/feed-util
License:    GPLv3+
Source:     https://example.org/feed-utils.tar

BuildArch:  noarch

Requires:   python3-defusedxml
Requires:   python3-CacheControl
Requires:   python3-html5lib
Requires:   python3-pycurl
Requires:   python3-requests

%description
Collection of RSS/Atom feed utilities.

%prep
%if %{with srpm}
%autosetup -n feed-utils
%endif

%build

%install
mkdir -p %{buildroot}/usr/bin
cp heiser.py %{buildroot}/usr/bin/heiser
cp lwn.py %{buildroot}/usr/bin/lwn
cp rss2atom.py %{buildroot}/usr/bin/rss2atom
cp betterflix.py %{buildroot}/usr/bin/betterflix


%check

%files
/usr/bin/heiser
/usr/bin/lwn
/usr/bin/rss2atom
/usr/bin/betterflix
%doc README.md


%changelog
* Mon Dec 12 2022 Georg Sauthoff <mail@gms.tf> - 0.6.0-1
- add betterflix movie feed generator

* Sat Jan 09 2021 Georg Sauthoff <mail@gms.tf> - 0.5.0-1
- fix lwn headline parsing
- remove latest heiser junk

* Sun Sep 06 2020 Georg Sauthoff <mail@gms.tf> - 0.5.0-1
- initial packaging

