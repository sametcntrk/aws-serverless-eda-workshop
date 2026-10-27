# Generates cloudformation/network.yaml (VPC, 3 AZ x 3 tiers, NAT per AZ, endpoints, SGs, VGW + VPN to the 3PL).
import sys
L = []
w = L.append
w("""AWSTemplateFormatVersion: '2010-09-09'
Description: Voltaj network - one VPC in 3 AZs (public, private-app, private-data), NAT per AZ, VPC endpoints, security groups, Site-to-Site VPN to the 3PL.
Resources:
  Vpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags: [{Key: Name, Value: voltaj-vpc}]
  Igw:
    Type: AWS::EC2::InternetGateway
    Properties:
      Tags: [{Key: Name, Value: voltaj-igw}]
  IgwAttach:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties: {VpcId: !Ref Vpc, InternetGatewayId: !Ref Igw}
  RtPublic:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref Vpc
      Tags: [{Key: Name, Value: rtb-voltaj-public}]
  RtPublicDefault:
    Type: AWS::EC2::Route
    DependsOn: IgwAttach
    Properties: {RouteTableId: !Ref RtPublic, DestinationCidrBlock: 0.0.0.0/0, GatewayId: !Ref Igw}
  RtData:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref Vpc
      Tags: [{Key: Name, Value: rtb-voltaj-private-data}]
  Vgw:
    Type: AWS::EC2::VPNGateway
    Properties:
      Type: ipsec.1
      Tags: [{Key: Name, Value: voltaj-vgw}]
  VgwAttach:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties: {VpcId: !Ref Vpc, VpnGatewayId: !Ref Vgw}
  RtData3pl:
    Type: AWS::EC2::Route
    DependsOn: VgwAttach
    Properties: {RouteTableId: !Ref RtData, DestinationCidrBlock: 172.16.0.0/16, GatewayId: !Ref Vgw}
  ThreePlEip:
    Type: AWS::EC2::EIP
    Properties:
      Domain: vpc
      Tags: [{Key: Name, Value: voltaj-3pl-cgw}]
  Cgw:
    Type: AWS::EC2::CustomerGateway
    Properties:
      Type: ipsec.1
      BgpAsn: 65000
      IpAddress: !Ref ThreePlEip
      Tags: [{Key: Name, Value: voltaj-3pl-cgw}]
  Vpn:
    Type: AWS::EC2::VPNConnection
    Properties:
      Type: ipsec.1
      StaticRoutesOnly: true
      CustomerGatewayId: !Ref Cgw
      VpnGatewayId: !Ref Vgw
      LocalIpv4NetworkCidr: 172.16.0.0/16
      RemoteIpv4NetworkCidr: 10.0.0.0/16
      Tags: [{Key: Name, Value: voltaj-vpn-3pl}]
  VpnRoute:
    Type: AWS::EC2::VPNConnectionRoute
    Properties: {VpnConnectionId: !Ref Vpn, DestinationCidrBlock: 172.16.0.0/16}
""")
pub = ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]
app = ["10.0.16.0/20", "10.0.32.0/20", "10.0.48.0/20"]
dat = ["10.0.64.0/22", "10.0.68.0/22", "10.0.72.0/22"]
for i, az in enumerate("ABC"):
    a = az.lower()
    w(f"""  Public{az}:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: {pub[i]}
      AvailabilityZone: !Select [{i}, !GetAZs '']
      Tags: [{{Key: Name, Value: voltaj-public-{a}}}]
  Public{az}Rt:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties: {{SubnetId: !Ref Public{az}, RouteTableId: !Ref RtPublic}}
  App{az}:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: {app[i]}
      AvailabilityZone: !Select [{i}, !GetAZs '']
      Tags: [{{Key: Name, Value: voltaj-private-app-{a}}}]
  Data{az}:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: {dat[i]}
      AvailabilityZone: !Select [{i}, !GetAZs '']
      Tags: [{{Key: Name, Value: voltaj-private-data-{a}}}]
  Data{az}Rt:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties: {{SubnetId: !Ref Data{az}, RouteTableId: !Ref RtData}}
  NatEip{az}:
    Type: AWS::EC2::EIP
    Properties:
      Domain: vpc
      Tags: [{{Key: Name, Value: voltaj-nat-{a}}}]
  Nat{az}:
    Type: AWS::EC2::NatGateway
    Properties:
      SubnetId: !Ref Public{az}
      AllocationId: !GetAtt NatEip{az}.AllocationId
      Tags: [{{Key: Name, Value: voltaj-nat-{a}}}]
  RtApp{az}:
    Type: AWS::EC2::RouteTable
    Properties:
      VpcId: !Ref Vpc
      Tags: [{{Key: Name, Value: rtb-voltaj-private-app-{a}}}]
  RtApp{az}Default:
    Type: AWS::EC2::Route
    Properties: {{RouteTableId: !Ref RtApp{az}, DestinationCidrBlock: 0.0.0.0/0, NatGatewayId: !Ref Nat{az}}}
  App{az}Rt:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties: {{SubnetId: !Ref App{az}, RouteTableId: !Ref RtApp{az}}}
""")
w("""  GwS3:
    Type: AWS::EC2::VPCEndpoint
    Properties:
      VpcId: !Ref Vpc
      VpcEndpointType: Gateway
      ServiceName: !Sub com.amazonaws.${AWS::Region}.s3
      RouteTableIds: [!Ref RtAppA, !Ref RtAppB, !Ref RtAppC, !Ref RtData]
  GwDynamoDb:
    Type: AWS::EC2::VPCEndpoint
    Properties:
      VpcId: !Ref Vpc
      VpcEndpointType: Gateway
      ServiceName: !Sub com.amazonaws.${AWS::Region}.dynamodb
      RouteTableIds: [!Ref RtAppA, !Ref RtAppB, !Ref RtAppC, !Ref RtData]
  SgEndpoints:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-endpoints
      GroupDescription: Interface VPC endpoints - HTTPS from the VPC
      VpcId: !Ref Vpc
      SecurityGroupIngress: [{IpProtocol: tcp, FromPort: 443, ToPort: 443, CidrIp: 10.0.0.0/16}]
      Tags: [{Key: Name, Value: sg-voltaj-endpoints}]
  SgLambda:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-lambda
      GroupDescription: VPC Lambda functions (payment, order, fulfillment, producer)
      VpcId: !Ref Vpc
      SecurityGroupEgress: [{IpProtocol: '-1', CidrIp: 0.0.0.0/0}]
      Tags: [{Key: Name, Value: sg-voltaj-lambda}]
  SgProxy:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-proxy
      GroupDescription: RDS Proxy - PostgreSQL from the VPC Lambda functions
      VpcId: !Ref Vpc
      SecurityGroupIngress: [{IpProtocol: tcp, FromPort: 5432, ToPort: 5432, SourceSecurityGroupId: !Ref SgLambda}]
      Tags: [{Key: Name, Value: sg-voltaj-proxy}]
  SgAurora:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-aurora
      GroupDescription: Aurora - PostgreSQL from RDS Proxy
      VpcId: !Ref Vpc
      SecurityGroupIngress: [{IpProtocol: tcp, FromPort: 5432, ToPort: 5432, SourceSecurityGroupId: !Ref SgProxy}]
      Tags: [{Key: Name, Value: sg-voltaj-aurora}]
  SgMq:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-mq
      GroupDescription: Amazon MQ RabbitMQ - AMQPS from Lambda, the 3PL network and Pipes; console from the VPC
      VpcId: !Ref Vpc
      SecurityGroupIngress:
        - {IpProtocol: tcp, FromPort: 5671, ToPort: 5671, SourceSecurityGroupId: !Ref SgLambda}
        - {IpProtocol: tcp, FromPort: 5671, ToPort: 5671, CidrIp: 172.16.0.0/16}
        - {IpProtocol: tcp, FromPort: 443, ToPort: 443, SourceSecurityGroupId: !Ref SgLambda}
      Tags: [{Key: Name, Value: sg-voltaj-mq}]
  SgMqSelf:
    Type: AWS::EC2::SecurityGroupIngress
    Properties: {GroupId: !Ref SgMq, IpProtocol: tcp, FromPort: 5671, ToPort: 5671, SourceSecurityGroupId: !Ref SgMq}
  SgMsk:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupName: voltaj-msk
      GroupDescription: MSK Serverless - IAM port 9098 from Lambda and from the event source mappings
      VpcId: !Ref Vpc
      SecurityGroupIngress: [{IpProtocol: tcp, FromPort: 9098, ToPort: 9098, SourceSecurityGroupId: !Ref SgLambda}]
      Tags: [{Key: Name, Value: sg-voltaj-msk}]
  SgMskSelf:
    Type: AWS::EC2::SecurityGroupIngress
    Properties: {GroupId: !Ref SgMsk, IpProtocol: tcp, FromPort: 9098, ToPort: 9098, SourceSecurityGroupId: !Ref SgMsk}
""")
for svc in ["events", "states", "sns", "sqs", "secretsmanager", "sts", "logs", "lambda", "pipes-data"]:
    rid = "Ep" + "".join(p.capitalize() for p in svc.split("-"))
    w(f"""  {rid}:
    Type: AWS::EC2::VPCEndpoint
    Properties:
      VpcId: !Ref Vpc
      VpcEndpointType: Interface
      ServiceName: !Sub com.amazonaws.${{AWS::Region}}.{svc}
      PrivateDnsEnabled: true
      SubnetIds: [!Ref AppA, !Ref AppB, !Ref AppC]
      SecurityGroupIds: [!Ref SgEndpoints]
""")
out = {"VpcId": "!Ref Vpc", "AppSubnets": "!Join [',', [!Ref AppA, !Ref AppB, !Ref AppC]]",
       "DataSubnets": "!Join [',', [!Ref DataA, !Ref DataB, !Ref DataC]]",
       "DataSubnetA": "!Ref DataA", "DataSubnetB": "!Ref DataB", "DataSubnetC": "!Ref DataC",
       "SgLambda": "!Ref SgLambda", "SgProxy": "!Ref SgProxy", "SgAurora": "!Ref SgAurora", "SgMq": "!Ref SgMq",
       "SgMsk": "!Ref SgMsk", "ThreePlEipAlloc": "!GetAtt ThreePlEip.AllocationId", "ThreePlEip": "!Ref ThreePlEip",
       "VpnId": "!Ref Vpn", "NatIps": "!Join [',', [!Ref NatEipA, !Ref NatEipB, !Ref NatEipC]]"}
w("Outputs:")
for k, v in out.items():
    w(f"  {k}:\n    Value: {v}\n    Export: {{Name: !Sub '${{AWS::StackName}}-{k}'}}")
open(sys.argv[1], "w").write("\n".join(L) + "\n")
