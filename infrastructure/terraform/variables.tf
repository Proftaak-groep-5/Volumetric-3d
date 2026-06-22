variable "region" {
  description = "AWS Region"
  default     = "eu-west-1"
}

variable "cluster_name" {
  description = "GitOpsPOC"
  default     = "gitops-cluster"
}

variable "environment" {
  default = "dev"
}