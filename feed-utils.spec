%bcond_without srpm


Name:       feed-utils
Version:    0.5.0
Release:    1%{?dist}
Summary:    Collection of RSS/Atom utilities
URL:        https://github.com/gsauthof/feed-util
License:    GPLv3+
Source:     https://example.org/feed-utils.tar


Requires:   python3-CacheControl
Requires:   python3-html5lib
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


%check

%files
/usr/bin/heiser
/usr/bin/lwn
/usr/bin/rss2atom
%doc README.md


%changelog
* Sun Sep 06 2020 Georg Sauthoff <mail@gms.tf> - 0.5.0-1
- initial packaging

