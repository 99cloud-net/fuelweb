class puppetmaster (
  $puppet_master_hostname,
  $puppet_stored_dbname = "puppet",
  $puppet_stored_dbuser = "puppet",
  $puppet_stored_dbpassword = "Johmek0mi9WeGhieshiFiB9rizai0M",
  $puppet_stored_dbsocket = "/var/lib/mysql/mysql.sock",
  $mysql_root_password = "eo6raesh7aThe5ahbahgohphupahk5",
  $puppet_package_version = "2.7.19-1.el6",
  $gem_source = "http://rubygems.org/",
  ) {
  anchor { "puppetmaster-begin": }
  anchor { "puppetmaster-end": }

  Anchor<| title == "puppetmaster-begin" |> ->
  Class["puppetmaster::selinux"] ->
  Class["puppetmaster::iptables"] ->
  Class["puppetmaster::mysql"] ->
  Class["puppetmaster::packages"] ->
  Class["puppetmaster::unicorn"] ->
  Class["puppetmaster::nginx"] ->
  Anchor<| title == "puppetmaster-end" |>


  class { "puppetmaster::selinux": }

  class { "puppetmaster::iptables": }

  class { "puppetmaster::mysql":
    puppet_stored_dbname => $puppet_stored_dbname,
    puppet_stored_dbuser => $puppet_stored_dbuser,
    puppet_stored_dbpassword => $puppet_stored_dbpassword,
    mysql_root_password => $mysql_root_password,
  }

  class { "puppetmaster::packages":
    puppet_package_version => $puppet_package_version,
    gem_source => $gem_source,
  }

  $puppet_master_ports = "18140"

  class { "puppetmaster::unicorn":
    puppet_master_hostname => $puppet_master_hostname,
    puppet_stored_dbname => $puppet_stored_dbname,
    puppet_stored_dbuser => $puppet_stored_dbuser,
    puppet_stored_dbpassword => $puppet_stored_dbpassword,
    puppet_stored_dbsocket => "/var/lib/mysql/mysql.sock",
    puppet_master_ports => $puppet_master_ports,
  }

  class { "puppetmaster::nginx":
    puppet_master_hostname => $puppet_master_hostname,
    puppet_master_ports => $puppet_master_ports,
  }

}
