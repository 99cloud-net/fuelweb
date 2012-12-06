class puppetmaster::packages(
  $puppet_package_version = "2.7.19-1.el6",
  $gem_source="http://rubygems.org/",

  $unicorn=true,
  ){

  define puppetmaster_safe_package($version = ""){
    if $version != "" {
      $ensure = $version
    }
    else {
      $ensure = "present"
    }

    if ! defined(Package[$name]){
      @package { $name :
        ensure => $ensure
      }
    }
  }

  puppetmaster_safe_package{ "mysql-devel": }
  puppetmaster_safe_package{ "ruby-devel": }
  puppetmaster_safe_package{ "rubygems": }
  puppetmaster_safe_package{ "make": }
  puppetmaster_safe_package{ "gcc": }
  puppetmaster_safe_package{ "gcc-c++": }

  puppetmaster_safe_package{ "puppet-server":
    version => $puppet_package_version,
  }
  puppetmaster_safe_package{ "rubygem-mongrel": }
  puppetmaster_safe_package{ "nginx": }


  Puppetmaster_safe_package<| title == "mysql-devel" |> ->
  Puppetmaster_safe_package<| title == "ruby-devel" |> ->
  Puppetmaster_safe_package<| title == "rubygems" |> ->
  Puppetmaster_safe_package<| title == "make" |> ->
  Puppetmaster_safe_package<| title == "gcc" |> ->
  Puppetmaster_safe_package<| title == "gcc-c++" |> ->

  Package<| provider == "gem" |> ->

  Puppetmaster_safe_package<| title == "rubygem-mongrel" |> ->
  Puppetmaster_safe_package<| title == "puppet-server" |>

  # http://projects.puppetlabs.com/issues/9290
  package { "rails":
    provider => "gem",
    ensure => "3.0.10",
    source => $gem_source,
  }

  package { "activerecord":
    provider => "gem",
    ensure => "3.0.10",
    source => $gem_source,
  }

  package { "mysql":
    provider => "gem",
    ensure => "2.8.1",
    source => $gem_source,
  }

  package { "unicorn":
    provider => "gem",
    ensure => "4.4.0",
    source => $gem_source,
  }

  package { "god":
    provider => "gem",
    ensure => "0.13.1",
    source => $gem_source,
  }

  package { "rack":
    provider => "gem",
    ensure => "1.2.5",
    source => $gem_source,
  }

  }
