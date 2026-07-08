variable "location" {
  description = "Azure region"
  type        = string
  default     = "koreacentral"
}

variable "resource_group_name" {
  type    = string
  default = "rg-akarstack"
}

variable "admin_username" {
  type    = string
  default = "uniska"
}

variable "ssh_public_key_path" {
  description = "Path to your local SSH public key (~/.ssh/id_rsa_azure.pub)"
  type        = string
  default     = "~/.ssh/id_rsa_azure.pub"
}

# var.my_ip dihapus — SSH port 2234 terbuka ke internet (0.0.0.0/0).
# Defense-in-depth: fail2ban (Ansible) akan ban 1 tahun untuk 1x gagal login.

variable "control_vm_size" {
  description = "k3s-server size (control-plane + single-node Ceph mon/OSD)"
  type        = string
  default     = "Standard_B2as_v2" # $0.09 2vcpu 8Gb Ram
}

variable "worker_vm_size" {
  description = "worker size (Flask apps + CephFS client only, no OSD)"
  type        = string
  default     = "Standard_B2as_v2" # $0.09 2vcpu 8Gb Ram
  #default     = "Standard_B2als_v2" # $0.05 2vcpu 4Gb Ram
}

variable "os_image" {
  description = "Ubuntu version - both 22.04 and 24.04 LTS work fine for k3s"
  type        = string
  default     = "24_04-lts-gen2" # change to "22_04-lts-gen2" if you prefer 22.04
}

variable "os_disk_size_gb" {
  description = "OS disk size for all VMs"
  type        = number
  default     = 32
}

variable "ceph_disk_size_gb" {
  description = "Ukuran disk untuk Ceph OSD di k3s-server (single-node, no HA)"
  type        = number
  default     = 8  
}

variable "ssh_port" {
  description = "Custom SSH port (moved off default 22)"
  type        = number
  default     = 22
  # default     = 2234
}

variable "worker_spot_max_price" {
  description = "Max hourly price you're willing to pay for worker spot VMs (-1 = pay up to on-demand price, never gets evicted purely for price reasons)"
  type        = number
  default     = 0.09
}
