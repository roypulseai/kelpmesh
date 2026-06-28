provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  default     = "briq"
}

variable "container_image" {
  description = "Docker image for briq runner"
  default     = "briq/runner:latest"
}

variable "cpu" {
  description = "CPU units for Fargate task"
  default     = 256
}

variable "memory" {
  description = "Memory MiB for Fargate task"
  default     = 512
}

# --- Networking ---

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "runner" {
  name        = "${var.project_name}-runner-sg"
  description = "briq runner tasks"

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- ECS Cluster ---

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "runner" {
  family                   = "${var.project_name}-runner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory

  container_definitions = jsonencode([
    {
      name         = "runner"
      image        = var.container_image
      essential    = true
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "runner"
        }
      }
      environment = [
        { name = "BRIQ_PROJECT_DIR", value = "/app/project" },
      ]
    }
  ])
}

resource "aws_ecs_service" "runner" {
  name            = "${var.project_name}-runner"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.runner.arn
  launch_type     = "FARGATE"
  desired_count   = 0

  network_configuration {
    subnets         = data.aws_subnets.default.ids
    security_groups = [aws_security_group.runner.id]
    assign_public_ip = true
  }
}

# --- CloudWatch ---

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 30
}

# --- IAM ---

resource "aws_iam_role" "execution" {
  name = "${var.project_name}-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "task_definition" {
  value = aws_ecs_task_definition.runner.arn
}
