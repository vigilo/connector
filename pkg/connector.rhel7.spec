%define module  @SHORT_NAME@

Name:       vigilo-%{module}
Summary:    @SUMMARY@
Version:    @VERSION@
Release:    @RELEASE@%{?dist}
Source0:    %{name}-%{version}.tar.gz
URL:        @URL@
Group:      Applications/System
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2
Buildarch:  noarch

BuildRequires:   python-setuptools
BuildRequires:   python-babel

Requires:   python-distribute
Requires:   vigilo-common
Requires:   python-zope-interface
Requires:   python-txamqp


%description
@DESCRIPTION@
This library is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q

%build

%install
rm -rf $RPM_BUILD_ROOT
make install_pkg \
    DESTDIR=$RPM_BUILD_ROOT \
    PREFIX=%{_prefix} \
    PYTHON=%{__python}

# Splitted Twisted
sed -i -e 's/^Twisted$/Twisted_Core/' $RPM_BUILD_ROOT%{_prefix}/lib*/python*/site-packages/vigilo*.egg-info/requires.txt

%find_lang %{name}


%clean
rm -rf $RPM_BUILD_ROOT

%files -f %{name}.lang
%defattr(644,root,root,755)
%doc COPYING.txt README.txt
%attr(755,root,root) %{_bindir}/*
%{python_sitelib}/*


%changelog
* Fri Jan 21 2011 Vincent Quéméner <vincent.quemener@c-s.fr>
- Rebuild for RHEL6.

* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr>
- initial package
