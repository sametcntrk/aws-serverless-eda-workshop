"""Writes the Libreswan config for tunnel 1 of the AWS Site-to-Site VPN from the customer gateway configuration."""
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import boto3

vpn_id, eip, private_ip = sys.argv[1:4]
ec2 = boto3.client("ec2", region_name="eu-central-1")
while True:
    v = ec2.describe_vpn_connections(VpnConnectionIds=[vpn_id])["VpnConnections"][0]
    if v.get("CustomerGatewayConfiguration") and v["State"] == "available":
        break
    time.sleep(20)
root = ET.fromstring(v["CustomerGatewayConfiguration"])
t = root.findall("ipsec_tunnel")[0]
outside = t.find("vpn_gateway/tunnel_outside_address/ip_address").text
psk = t.find("ike/pre_shared_key").text
open("/etc/ipsec.d/aws.conf", "w").write(f"""conn aws-tunnel1
    authby=secret
    auto=start
    left=%defaultroute
    leftid={eip}
    leftsourceip={private_ip}
    leftsubnet=172.16.0.0/16
    right={outside}
    rightsubnet=10.0.0.0/16
    type=tunnel
    ikev2=insist
    ike=aes256-sha2_256;dh14
    phase2alg=aes256-sha2_256;dh14
    ikelifetime=8h
    salifetime=1h
    dpddelay=10
    dpdtimeout=30
    dpdaction=restart
""")
open("/etc/ipsec.d/aws.secrets", "w").write(f'{eip} {outside} : PSK "{psk}"\n')
subprocess.run(["chmod", "600", "/etc/ipsec.d/aws.secrets"], check=True)
print("tunnel 1:", outside)
