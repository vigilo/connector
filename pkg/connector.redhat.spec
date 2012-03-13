%define module  @SHORT_NAME@

%define pyver 26
%define pybasever 2.6
%define __python /usr/bin/python%{pybasever}
%define __os_install_post %{__python26_os_install_post}
%{!?python26_sitelib: %define python26_sitelib %(python26 -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:       vigilo-%{module}
Summary:    @SUMMARY@
Version:    @VERSION@
Release:    @RELEASE@%{?dist}
Source0:    %{name}-%{version}.tar.gz
URL:        @URL@
Group:      System/Servers
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2
Buildarch:  noarch

BuildRequires:   python26-setuptools
BuildRequires:   python26-babel

Requires:   python26-distribute
Requires:   vigilo-common
Requires:   python26-zope-interface
Requires:   python26-txamqp
Requires:   python26-argparse


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
%{python26_sitelib}/*


%changelog
* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr>
- initial package
