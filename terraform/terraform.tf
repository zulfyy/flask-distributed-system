terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

# ---------------- Networking ----------------
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-akarstack"
  address_space       = ["10.10.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_subnet" "subnet" {
  name                 = "subnet-nodes"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.10.1.0/24"]
}

# ---------------- NSG (security) ----------------
# SSH port 2234 terbuka ke internet (0.0.0.0/0) karena var.my_ip sudah dihapus.
# Defense-in-depth: fail2ban (Ansible) akan ban 1 tahun untuk 1x gagal login.
resource "azurerm_network_security_group" "nsg" {
  name                = "nsg-akarstack"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  security_rule {
    name                       = "Allow-SSH-Public"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.ssh_port) # 22 by default
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-SSH-Hardened"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "2234"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Allow-HTTP-HTTPS-Public"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# ---------------- Public IP (Hanya untuk k3s-server) ----------------
resource "azurerm_public_ip" "pip_server" {
  name                = "pip-k3s-server"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# ---------------- NICs ----------------
locals {
  vm_names = toset(["k3s-server", "worker-1", "worker-2"])

  # k3s-server WAJIB IP privat yang fixed (bukan Dynamic) - dipakai hardcoded
  # sebagai NFS server address di k8s/01-storage.yaml. Kalau Dynamic, IP ini
  # bisa berubah tiap kali VM di-recreate (misal abis `terraform destroy` +
  # `apply` lagi buat hemat biaya - lihat README bagian Destroy), dan bikin
  # PV NFS diam-diam nunjuk ke IP yang salah/gak ada.
  # Worker-1/worker-2 dibiarkan Dynamic karena gak ada yang hardcode IP mereka
  # (inventory.ini pakai `terraform output public_ips` yang selalu up-to-date).
  static_private_ips = {
    "k3s-server" = "10.10.1.6"
  }
}

resource "azurerm_network_interface" "nic" {
  for_each            = local.vm_names
  name                = "nic-${each.key}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = contains(keys(local.static_private_ips), each.key) ? "Static" : "Dynamic"
    private_ip_address            = lookup(local.static_private_ips, each.key, null)
    # Hanya k3s-server yang mendapat Public IP
    public_ip_address_id = each.key == "k3s-server" ? azurerm_public_ip.pip_server.id : null
  }
}

resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  for_each                  = azurerm_network_interface.nic
  network_interface_id      = each.value.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}

# ---------------- Virtual Machines ----------------
# k3s-server: DEDICATED (on-demand, never evicted)
# Ceph OSD disk di-attach di sini (single-node Ceph, no HA)
resource "azurerm_linux_virtual_machine" "control" {
  name                = "k3s-server"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = var.control_vm_size
  admin_username      = var.admin_username
  priority            = "Regular"
  disable_password_authentication = true

  network_interface_ids = [azurerm_network_interface.nic["k3s-server"].id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# worker-1: DEDICATED (Flask apps, no eviction risk)
# worker-2: SPOT (cheap, ok to be evicted)
# Workers do NOT host Ceph OSD; they only mount CephFS volumes (uploads/results)
locals {
  worker_configs = {
    "worker-1" = {
      priority        = "Regular"
      eviction_policy = null
      max_bid_price   = null
    }
    "worker-2" = {
      priority        = "Spot"
      eviction_policy = "Deallocate"
      max_bid_price   = var.worker_spot_max_price
    }
  }
}

resource "azurerm_linux_virtual_machine" "worker" {
  for_each            = local.worker_configs
  name                = each.key
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = var.worker_vm_size
  admin_username      = var.admin_username

  priority        = each.value.priority
  eviction_policy = each.value.eviction_policy
  max_bid_price   = each.value.max_bid_price
  disable_password_authentication = true

  network_interface_ids = [azurerm_network_interface.nic[each.key].id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# ---------------- Ceph OSD disk (single-node, attached to k3s-server only) ----------------
resource "azurerm_managed_disk" "ceph_osd_disk" {
  name                 = "osd-disk-k3s-server"
  location             = azurerm_resource_group.rg.location
  resource_group_name  = azurerm_resource_group.rg.name
  storage_account_type = "Standard_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.ceph_disk_size_gb
}

resource "azurerm_virtual_machine_data_disk_attachment" "ceph_osd_attach" {
  managed_disk_id    = azurerm_managed_disk.ceph_osd_disk.id
  virtual_machine_id = azurerm_linux_virtual_machine.control.id
  lun                = "10"
  caching            = "None"
}

# ---------------- Outputs ----------------
output "public_ips" {
  value = {
    "k3s-server" = azurerm_public_ip.pip_server.ip_address
    "worker-1"   = azurerm_network_interface.nic["worker-1"].private_ip_address
    "worker-2"   = azurerm_network_interface.nic["worker-2"].private_ip_address
  }
}

output "ceph_osd_disk" {
  description = "Raw block device Rook-Ceph will claim on k3s-server (find via `lsblk`, usually /dev/sdc)"
  value       = azurerm_managed_disk.ceph_osd_disk.name
}

output "ssh_command_hint" {
  value = <<-EOT
    Server  : ssh -p ${var.ssh_port} ${var.admin_username}@${azurerm_public_ip.pip_server.ip_address}

    Workers : ssh -p ${var.ssh_port} -o ProxyJump=${var.admin_username}@${azurerm_public_ip.pip_server.ip_address} ${var.admin_username}@<worker-private-ip>

    Server private IP (pakai ini buat "server:" di 01-storage.yaml, NFS): ${azurerm_network_interface.nic["k3s-server"].private_ip_address}

    (Note: Worker private IPs are listed in the 'public_ips' output above)
  EOT
}