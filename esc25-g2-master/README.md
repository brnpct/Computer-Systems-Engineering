# esc25-g2

im going to explain function calling here (forgive me for the delay on pushing this README)

we have a security group on our EC2 instance that accepts connections to port 9999 and 5000 (for the interface)

we have a config.sh with

export AWS_ACCESS_KEY_ID=censored
export AWS_SECRET_ACCESS_KEY=censored
export AWS_DEFAULT_REGION=eu-west-2

we also have these files

esc25keypair.pem
esc25keypair.pem:Zone.Identifier
rootkey.csv
rootkey.csv:Zone.Identifier

to launch the server to the instance we do

bash start-service.sh
(this takes a while since it needs to install packages)

at the end we open up the webpage on

http://instance_ip:5000/

from here we can just press fresh start and it will be up and running
ec2 instance has to be terminated manually afterwards


for the client.py the usage is exactly as outlined in the enunciado

for the flask interface we do this:

python app.py port server_ip
              ^^^^
    different than 5000 and 9999

then we just have to go to 

http://127.0.0.1:port/

and it's fairly self-explanatory from there
multiple interface instances must be on different browers

for the stress testing we do this:

python stress_test.py server_ip target_topic number_of_users time_between_random_messages