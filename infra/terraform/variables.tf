variable "tenancy_ocid" {
  type        = string
  description = "OCID of the tenancy (OCI console: Tenancy details)."
}

variable "user_ocid" {
  type        = string
  description = "OCID of the user that owns the API key."
}

variable "fingerprint" {
  type        = string
  description = "Fingerprint of the API signing key."
}

variable "private_key_path" {
  type        = string
  description = "Path to the API signing private key (PEM)."
}

variable "region" {
  type        = string
  description = "Home region, e.g. eu-stockholm-1. Always Free compute exists only there."
}

variable "ssh_public_key" {
  type        = string
  description = "Public key allowed to log in as the default 'ubuntu' user."
}

variable "admin_cidr" {
  type        = string
  description = "Only this address range may use SSH, e.g. your IP as 203.0.113.7/32."

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "Use a specific range for SSH, not the whole internet."
  }
}

variable "budget_alert_email" {
  type        = string
  description = "Receives an email as soon as anything starts costing money."
}

variable "availability_domain_index" {
  type        = number
  default     = 0
  description = "Try another index if the region reports no free Ampere capacity."
}

# Always Free allows up to 4 OCPUs / 24 GB for Ampere A1 in total. Half of it is plenty
# for FleetPulse and leaves room for a second VM.
variable "ocpus" {
  type    = number
  default = 2
}

variable "memory_gbs" {
  type    = number
  default = 12
}

variable "boot_volume_gbs" {
  type    = number
  default = 50 # Always Free includes 200 GB of block storage in total
}
