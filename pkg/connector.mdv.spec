%define module  connector
%define name    vigilo-%{module}
%define version 1.1
%define release 1%{?svn}

Name:       %{name}
Summary:    Vigilo XMPP connector library
Version:    %{version}
Release:    %{release}
Source0:    %{module}.tar.bz2
URL:        http://www.projet-vigilo.org
Group:      System/Servers
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2

BuildRequires:   python-setuptools

Requires:   python >= 2.5
Requires:   python-setuptools
Requires:   vigilo-common vigilo-pubsub
Requires:   python-twisted-words
Requires:   python-wokkel

Requires(pre): rpm-helper

Buildarch:  noarch


%description
This library gives an API to create an XMPP connector for Vigilo.
This library is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q -n %{module}

%build
make PYTHON=%{_bindir}/python

%install
rm -rf $RPM_BUILD_ROOT
make install \
	DESTDIR=$RPM_BUILD_ROOT \
	PREFIX=%{_prefix} \
	PYTHON=%{_bindir}/python

# Mandriva splits Twisted
sed -i -e 's/^Twisted$/Twisted_Words/' $RPM_BUILD_ROOT%{_prefix}/lib*/python*/site-packages/vigilo_connector-*-py*.egg-info/requires.txt


%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root)
%doc COPYING
%{python_sitelib}/*


%changelog
* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr> - 1.0-1
- initial package
