# AWS Deployment Guide for Meta-Data-Tag-Generator

Complete guide to deploy the application on AWS EC2 with CI/CD using GitHub Actions.

## Prerequisites

- AWS Account
- GitHub Account
- Domain name (optional, for custom domain)
- Basic knowledge of AWS EC2, ECR, and Docker

## Architecture

```
GitHub → GitHub Actions → AWS ECR → AWS EC2
                          (Docker Images)  (Running Containers)
```

**Components:**
- **EC2 Instance**: Hosts Docker containers
- **ECR (Elastic Container Registry)**: Stores Docker images
- **GitHub Actions**: CI/CD pipeline
- **Docker Compose**: Orchestrates containers
- **Nginx** (optional): Reverse proxy

## Step 1: Create ECR Repositories

```bash
# Login to AWS CLI
aws configure

# Create repositories for backend and frontend
aws ecr create-repository --repository-name meta-tag-backend --region us-east-1
aws ecr create-repository --repository-name meta-tag-frontend --region us-east-1

# Note down the repository URIs
```

## Step 2: Launch EC2 Instance

### Recommended Instance Type
- **Testing/Development**: `t3.medium` (2 vCPU, 4 GB RAM)
- **Production**: `t3.large` or higher (2 vCPU, 8 GB RAM)

### Steps:
1. Go to AWS EC2 Console
2. Click "Launch Instance"
3. **Configuration:**
   - **Name**: meta-tag-generator-server
   - **AMI**: Ubuntu Server 22.04 LTS
   - **Instance type**: t3.medium
   - **Key pair**: Create or select existing (download .pem file)
   - **Network settings**: 
     - Allow SSH (port 22) from your IP
     - Allow HTTP (port 80) from anywhere
     - Allow HTTPS (port 443) from anywhere
   - **Storage**: 30 GB gp3 (minimum)
4. Launch instance
5. Note down the **Public IPv4 address**

## Step 3: Setup EC2 Instance

### Connect to EC2
```bash
# Change permissions on your key file
chmod 400 your-key.pem

# SSH into instance
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

### Run Initial Setup Script
```bash
# Copy setup script to EC2
scp -i your-key.pem deployment/setup-ec2.sh ubuntu@YOUR_EC2_PUBLIC_IP:~/

# SSH into EC2 and run setup
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
chmod +x setup-ec2.sh
./setup-ec2.sh

# Log out and log back in for Docker group changes
exit
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

## Step 4: Configure GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add these secrets:

| Secret Name | Value | How to Get |
|-------------|-------|------------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key | AWS IAM Console |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | AWS IAM Console |
| `AWS_ACCOUNT_ID` | Your AWS account ID | Top right in AWS Console |
| `EC2_HOST` | EC2 public IP | EC2 Console |
| `EC2_USER` | `ubuntu` | Default for Ubuntu AMI |
| `EC2_SSH_PRIVATE_KEY` | Content of .pem file | Your downloaded key file |

### Creating IAM User for GitHub Actions

1. Go to AWS IAM Console
2. Create new user: `github-actions-deployer`
3. Attach policies:
   - `AmazonEC2ContainerRegistryPowerUser` (for ECR)
   - Custom policy for ECR login:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ecr:GetAuthorizationToken",
           "ecr:BatchCheckLayerAvailability",
           "ecr:GetDownloadUrlForLayer",
           "ecr:BatchGetImage",
           "ecr:PutImage",
           "ecr:InitiateLayerUpload",
           "ecr:UploadLayerPart",
           "ecr:CompleteLayerUpload"
         ],
         "Resource": "*"
       }
     ]
   }
   ```
4. Create access key and save credentials

## Step 5: Initial Manual Deployment

Before setting up CI/CD, do a manual deployment to verify everything works:

```bash
# On your local machine, build and push images manually
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push backend
cd backend
docker build -t YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/meta-tag-backend:latest .
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/meta-tag-backend:latest

# Build and push frontend
cd ../frontend
docker build -t YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/meta-tag-frontend:latest .
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/meta-tag-frontend:latest

# SSH to EC2 and deploy
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

# On EC2, update docker-compose.yml to use ECR images
cd ~/meta-tag-generator
# Edit docker-compose.yml to reference ECR images

# Deploy
./deploy.sh
```

## Step 6: Enable CI/CD

Once manual deployment works:

1. Push your code to GitHub (main/master branch)
2. GitHub Actions will automatically:
   - Build Docker images
   - Push to ECR
   - Deploy to EC2
3. Monitor in GitHub Actions tab

### Trigger Manual Deployment
Go to Actions tab → Deploy to AWS EC2 → Run workflow

## Step 7: Configure Domain (Optional)

### Using Route 53:
1. Register or transfer domain to Route 53
2. Create hosted zone
3. Create A record pointing to EC2 public IP
4. Update Nginx config with your domain
5. Setup SSL with Let's Encrypt:
   ```bash
   # On EC2
   sudo apt-get install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

## Step 8: Monitoring and Maintenance

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Restart Services
```bash
docker-compose restart
```

### Update Application
```bash
# Pull latest changes
git pull origin main

# Redeploy
./deploy.sh
```

### System Monitoring
```bash
# Docker stats
docker stats

# Disk usage
df -h

# Memory usage
free -m
```

## Cost Estimation (Testing Phase)

**Monthly costs (us-east-1):**
- EC2 t3.medium: ~$30/month
- 30 GB EBS storage: ~$3/month
- ECR storage (< 10 GB): ~$1/month
- Data transfer (minimal): ~$1-5/month

**Total: ~$35-40/month**

### Cost Optimization:
- Use EC2 spot instances (70% cheaper)
- Stop instance when not in use
- Use AWS Free Tier if eligible (12 months)

## Troubleshooting

### Container won't start
```bash
docker-compose logs backend
docker-compose logs frontend
```

### Out of memory
Upgrade to t3.large or add swap:
```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### ECR authentication issues
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

### GitHub Actions deployment fails
- Check EC2 security group allows SSH from GitHub IPs
- Verify all GitHub secrets are set correctly
- Check EC2 has enough disk space: `df -h`

## Security Best Practices

1. **Use Security Groups**: Only allow necessary ports
2. **Regular Updates**: Keep EC2 and Docker updated
3. **SSH Key Management**: Rotate keys regularly
4. **IAM Permissions**: Use least privilege principle
5. **SSL/TLS**: Always use HTTPS in production
6. **Secrets Management**: Use AWS Secrets Manager for sensitive data
7. **Backups**: Regular backups of data and configs

## Scaling Considerations

When you need more capacity:

1. **Vertical Scaling**: Upgrade EC2 instance type
2. **Load Balancer**: Add ALB for multiple instances
3. **Auto Scaling**: Use Auto Scaling Groups
4. **Database**: Add RDS for persistent data
5. **Cache**: Add ElastiCache for better performance
6. **CDN**: Use CloudFront for static assets

## Support

For issues or questions:
- Check logs: `docker-compose logs`
- Review GitHub Actions workflow runs
- Check AWS CloudWatch logs
- Review this guide again

## Quick Reference Commands

```bash
# Deploy application
./deploy.sh

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Start services
docker-compose up -d

# Check service status
docker-compose ps

# Clean up old images
docker image prune -af

# Check disk space
df -h

# Check memory
free -m

# Update from GitHub
git pull && ./deploy.sh
```

