output "public_ip" {
  description = "Point the domain's DNS record here."
  value       = oci_core_instance.app.public_ip
}

output "ssh" {
  value = "ssh ubuntu@${oci_core_instance.app.public_ip}"
}
