# Route 53 hosted zone for the custom domain.
# NIC.ar (the .ar registry) does not host DNS zones, so we delegate: the four
# name_servers below are entered into nic.ar's "Delegación" for the domain.
# ~$0.50/mo per hosted zone — within the budget.
resource "aws_route53_zone" "main" {
  name = var.domain
}

# www is the primary hostname; apex redirects to www at the app/Caddy layer.
resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "www.${var.domain}"
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}

resource "aws_route53_record" "apex" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}

output "route53_nameservers" {
  description = "Enter these as the domain's nameservers in nic.ar (Delegación)."
  value       = aws_route53_zone.main.name_servers
}
