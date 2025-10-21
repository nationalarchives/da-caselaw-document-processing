terraform {
  backend "s3" {
    bucket       = var.backend_bucket
    key          = "terraform/state/da-caselaw-document-processing.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
