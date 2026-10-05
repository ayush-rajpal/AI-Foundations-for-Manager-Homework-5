# AI Prompts — Homework 5

## Problem 1: Vibe coder prompts

### Prompt 1

```text
create AI_prompts.md file - it will record all prompts given by me - record my prompts word to word without any change. we are working on homework 5 which is divided into 11 problems - this prompt is part of Problem 1 so record this prompt in AI_prompts.md file as well under Problem 1: Vibe coder prompts
```

## Problem 2: Study the campus customs database

### Prompt 1

```text
we are moving to problem 2: study the campus customs database
```

### Prompt 2

```text
go through the data/campus_customs.db - all the table and fields. Copy this db to data/campus_customs_new.db. go through the three open tickets and mention about them in chat as well - I want to see how they link to other tables. create a output/harness.md file and for each table, list all the fields and why that field (1-2 line) matters for the agents. Just for your context (do not do anything for this): today we are building campus customs Multi-Agent Operations team which is the agentic team that runs the shop.
```

## Problem 3: Build the MCP server

### Prompt 1

```text
we are moving to problem 3: build the mcp server
```

### Prompt 2

```text
build a  MCP server in mcp_server/ using FastMCP. It will talk to data/campus_customs_new.db. all the agent we will build for this hw uses the tools in the MCP server. after creating the mcp server - create 3 tools you we need for solving the tickets we saw in problem 2. ensure the names of the tools are short and represent their function. DO NOT CREATE ANY DATA -  only use information in the database. In output/harness.md, list all 3 tools and write about which table the tools reads, which ticket it helps unlock (101, 102, or 103), and 1 lineon why that tool is the right one for that ticket - 1 line should shoube be compresenhive . Also create a mcp_server/README.md file that explains what the mcp server is for, which database file it uses, and the 3 tools it has - also mention these on chat so I understand as well
```

## Problem 4: Add the MCP server to vibe coder and test each tool

### Prompt 1

```text
we are moving to problem 4: add the MCP server to vibe coder and test each tool
```

### Prompt 2

```text
add the MCP server to this project so the you can call the tools we built in the last problem. save the connection json text in .mcp.json at the project root.
```

### Prompt 3

```text
you connected now and can call the tools?
```

### Prompt 4

```text
activate the campus customs mcp server
```
### Prompt 5

```text
Use the check_stock tool to check the stock quantity, cost, and list price for SKU 'CC-HOOD-NAVY' in size 'M'
```

### Prompt 6

```text
Use the check_invoice tool to check the details, vendor status, and payment standing for invoice 501
```

### Prompt 7

```text
Use the check_rent tool to check the lease details, monthly rent amount, and payment due date for lease 1
```

### Prompt 8

```text
save the evidence of running these three tools into output/mcp_smoke.json - include the exact prompt asked, the tool name, and the tool output matching the database values for each tool
```

## Problem 5: Build the agent team and grow the MCP tools

### Prompt 1

```text
we will move to problem 5: build the agent team and grow the MCP tools
```

### Prompt 2

```text
we need to setup the 5 agents now using pydanticai with full connectivity so any agent can delegate to any other - put data types in backend/models.py and create one prompt file per agent inside backend/prompts and make sure to use gpt-6-luna with portkey api key (.env file)

1.  Boss agent: orchestrates the whole shop, reads incoming tickets, determines which agent handles what, delegates tasks, reviews findings, makes final calls, and ensures no ticket is marked resolved without every constraint satisfied
2. Inventory agent: looks up stock levels by sku and size, identifies inventory shortfalls, matches items to suppliers, checks vendor lead times from the vendors table, and enforces the rule that a vendor will never ship restocks if they have an open unpaid invoice
3.  Accounting agent: watches cash balances, checks margins, validates discounts against list prices and unit costs, verifies open invoices, strictly checks overdue dates using desk.date_today, prepares payment orders for human approval, and refuses any payment if cash balance would drop below zero
4.  Facilities agent: handles physical store space, reviews leases and rent amounts, checks payment due dates against desk.date_today, and confirms rent amounts from actual lease records rather than ticket text
5.  Customer Service agent: drafts clear responses to customers - explains delays, policies, or discounts, and enforces the rule to never send real emails or contact customers directly since all drafts stay on the internal board
```

### Prompt 3

```text
now we need to add whatever extra tools the agents need to our mcp server so they can handle the tickets make sure all database queries go through mcp reading data/campus_customs_new.db and do not make any tools outside mcp that bypass it then update mcp_server/README.md with the full list of tools and the tables they touch
```

### Prompt 4

```text
ensure that whenever any agent takes an action or delegates to another agent it appends the log into output/audit_trail.json  - make sure it appends every step and does not overwrite or wipe the file between runs
```

### Prompt 5

```text
in output/harness.md and document all 5 agents and all the mcp tool along with the database tables each tool reads or writes then add a safety section describing the guardrails for handling money, customer replies and token use such that agents are not going into infinite loop and burning tokens
```

## Problem 6: Plan the 3 tickets

### Prompt 1

```text
we moving to problem 6: plan the 3 tickets
```

### Prompt 2

```text
make output/desk_tickets.html - it should be a clean interactive page with tabs for ticket 101, ticket 102, ticket 103, plus two placeholder tabs for cash and reflection with a simple coming later note on those two

for each ticket tab make two distinct areas: one for expected and one for actual  - leave actual empty for now

in the expected section for each ticket put the following:

ticket 101:
- boss first call: boss calls inventory first because this is a customer merchandise order so checking stock for sku CC-TEE-WHITE size s is initial operational step
- delegation flow: inventory checks stock and finds 0 units then sees restocking depends on overdue invoice 501 for bulldog print co inventory directly delegates to accounting to handle the blocker accounting confirms cash covers the 840 dollar invoice and drafts a payment approval request for the human then accounting delegates to customer service to draft a note explaining the 5 day reprint timeline 
- expected mcp tools: check_stock, check_invoice, check_cash

ticket 102:
- boss first call: boss calls facilities first because ticket 102 is a facility notice regarding store space and lease terms
- delegation flow: facilities checks lease 1 in the database to verify the actual contract rent of 2400 dollars and due date then delegates directly to accounting to verify available cash of 3400 dollars and prepare the payment request for human signoff 
- expected mcp tools: check_rent, check_cash

ticket 103:
- boss first call: boss calls inventory first because yale ai club wants 20 hoodies so stock availability must be checked before discussing pricing
- delegation flow: inventory checks stock for cc-hood-navy size m and finds only # of units in stock inventory delegates directly to accounting to review unit cost of each hoodie to set bulk discounts, accounting also checks how much cash it has and how much more of inventory it can buy such that cash is not less than 0, then prepares a purchase order for human approval, accounting then delegates directly to customer service to draft a proposal offering the available units at the approved discount rate 
- expected mcp tools: check_stock, check_pricing
```

## Problem 7: Backend routes

### Prompt 1

```text
we are moving to problem 7: backend routes
```

### Prompt 2

```text
we need to set up fastapi in backend/main now so our frontend can connect to our agents and database
we need routes for these exact things:

1. get route to return the three tickets and if each one is open or resolved
2. post route that takes a ticket id and runs the agent team on that ticket
3. get route to fetch recent events like what agents said and tools they used so the dashboard can refresh
4. post route for approving payments because agents must only draft payments and this route is the only place that actually changes cash in cash_accounts and marks the invoice or lease table updated so there are no silent pays
5. get route to check the current checking balance from cash_accounts
6. route to reset the database by copying clean data/campus_customs.db over data/campus_customs_new.db for a fresh run
```

### Prompt 3

```text
update output/harness.md to document all of these backend routes - create a new section for this - write one line description with URL and what it does
```

## Problem 8: Agent dashboard

### Prompt 1

```text
moving to problem 8: agent dashboard
```

### Prompt 2

```text
we need to set up the frontend in frontend/ using react vite and typescript 
it needs to connect to our fastapi backend at http://localhost:8000 and do these things at minimum:
- show all three tickets on the desk
- let me select a ticket and trigger the agent team to run on it
- display live activity showing each agent speaking and what tools they execute while running
- mark tickets as resolved once the agents finish
- show a summary card for each agent explaining what they did on that ticket run
- include an approval action so a human can approve payments or purchases when accounting requests it
- display the checking account balance prominently and show it decrease when payments are approved
make the layout look creative and polished rather than the default vite template so it feels like a real desk dashboard - this is really dashboard I will be interac ting with so make it accessable as well
```

### Prompt 3

```text
write in output/design.md explaining the dashboard design choices describe the overall desk layout why we picked it how each agent is styled differently so they are easy to tell apart how ticket status and cash balance updates are displayed and what creative decisions make the interface feel intuitive and practical for a human operator
```

### Prompt 4

```text
is the dashboard ready yet
```

### Prompt 5

```text
its taking too long - get it done within next 5 minutes
```

### Prompt 6

```text
what happened here - I tried to run it but did not see output on the frotend
```

### Prompt 7

```text
update the frontend: 

Give each agent a distinct theme color: Assign a unique color to each of the five specialists (for example, gold for the Boss, blue for Inventory, green for Accounting, orange for Facilities, and purple for Customer Service). Use these colors consistently across their live activity logs, icons, and crew cards so you can see who is speaking at a single glance.Tuck raw database text into collapsible drop-downs: The live activity stream currently shows raw database code and curly brackets from tool outputs. Shorten these entries to a simple description like "Boss ran list_tickets" and place the raw technical details inside a clickable "View data" accordion so the feed stays clean and readable.Show an interactive cash balance meter: Alongside the raw numbers for your checking account, include a visual progress bar that displays your starting cash ($3,400) versus upcoming expenses. When a payment is drafted, highlight the deducted amount in amber or red to show the exact balance that will remain after approval.Add a visual delegation flowchart: In the crew section, display simple directional arrows between the cards (such as Boss $\rightarrow$ Inventory $\rightarrow$ Accounting) that light up when one agent hands a task to another. This illustrates multi-agent teamwork much better than static cards.Turn payment approvals into an eye-catching action card: When Accounting creates a draft, make the approval area pop out with a clear approval card. Display the vendor name, the exact dollar amount, the reason, and a prominent "Approve Payment" button so the user cannot miss human sign-off requests.Provide a ticket resolution summary box: When a ticket moves from "Open" to "Resolved", place a clean summary card at the top of the ticket view. This card should clearly explain the final outcome in plain language (such as "Bulldog Print Co invoice queued for payment; 5-day reprint will begin once cleared") so you do not need to hunt through logs to see what was decided.Add an auto-scroll toggle for the live feed: Because the agents generate updates rapidly, add a small toggle button to pause or enable auto-scrolling. This prevents the feed from jumping around while you are trying to read earlier messages.Upgrade the ticket selector into Kanban-style cards: Replace the simple list of tickets with distinct cards displaying status tags (such as a spinning icon for "In Progress", a yellow tag for "Awaiting Sign-off", and a green checkmark for "Resolved").
```

### Prompt 8

```text
when I approve a payment - I have to rerun the agent for ticket 1 - make it such that after my approvel it reruns own its own for that specfific ticket
```

### Prompt 9

```text
also to read the draft email I have to scroll down - have a pop appear that I can X after I read the email in the frontend
```

## Problem 9: Resolve the tickets

### Prompt 1

```text
we will mnove to problem 9: resove the tickets
```

### Prompt 2

```text
I will run the 3 tickets on front end - I want you to update the output/desk_tickets.html - fill the actual section - which agents actually ran,  what they delegated and which tools they used. Keep the expected section as it is!
```

### Prompt 3

```text
all 3 tickets are done
```

### Prompt 4

```text
also update the cash tab in output/desk_tickets.html to show:

* starting checking balance after the reset
* per ticket cash deduction and the reason why money was spent
* final ending balance matching cash_accounts in data/campus_customs_new.db exactly - also give a note if the ending balance match
```

### Prompt 5

```text
create - output/resolved_tickets.json — for each ticket: id, final status, short outcome, what each agent contributed, all human approvals and output/resolved_board.html with a screenshot of each tickets - I have pasted them
```

### Prompt 6

```text
add runs to output/audit_trail.json. and finally updayte the output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.
```

## Problem 10: Reflections

### Prompt 1

```text
we are moving to problem 10: reflections
```

### Prompt 2

```text
fill the reflection tab in output/desk_tickets.html:
Performance Evaluation of the Agents by Ticket
Overall, I think the agent team performed well because it focused on following the right process and finding alternatives within the restrictions of design rather than simply trying to resolve every ticket as quickly as possible.
For Ticket 101, Inventory correctly identified that size S was completely out of stock and also identified that Bulldog Print Co. was blocked because of the overdue $840 invoice. Instead of trying to bypass the payment requirement or contact the customer directly, Accounting drafted the $840 invoice payment and then the $8 replacement tee purchase, both of which were sent for human approval. After human approval, the Boss asked the customer service to draft and email and Customer Service drafted an internal reply with in-stock alternatives (Basic Hoodie Big Yale in size S for $58).
For Ticket 102, Facilities verified the $2,400 rent directly using the lease database rather than relying only on the ticket details. Accounting then checked that there was enough cash before drafting the payment. Once the $2,400 payment was approved, the Boss correctly marked the ticket as resolved because the full contractual obligation had been met.
For Ticket 103, the team had to deal with a more difficult cash constraint. Yale AI Club wanted 20 hoodies, but only 8 were in stock, and restocking all 12 would have cost $264, while only $152 was available in cash. Instead of simply rejecting the request, Accounting and Inventory found a middle ground by drafting a restock of 6 hoodies for $132, leaving $20 in cash ensuring the cash balance does not go below 0, while also approving a 10% bulk discount ($52.20 each, preserving a $30.20 unit margin). After this was approved, Customer Service drafted a message explaining that 14 total hoodies were accounted for (8 on hand, 6 arriving September 5, 2026), offering in-stock Bulldog tees as an alternative, and asking the customer how they would like to proceed.
Actual vs. Expected Delegation Plans
For Ticket 101, our expected plan was a straightforward Boss → Inventory → Accounting → Customer Service sequence that would finish in one continuous flow. In practice, the run had to be broken into three separate phases because of human approval gates. In Run 1, Boss called Inventory, found the stock shortfall and the overdue vendor blocker, and then called Accounting to draft the $840 invoice payment. Once that payment was approved by the human, Run 2 started automatically, where Boss brought Accounting back in to draft the $8 replacement purchase. After that second approval went through, Run 3 kicked off with Boss handing off to Customer Service, who then talked in Inventory to check in-stock alternatives before drafting the final reply to the customer.
For Ticket 102, the actual flow was very close to what we expected, but with more back-and-forth and duplicate tool calls. We thought Boss would hand off to Facilities, Facilities would check the lease and pass the numbers to Accounting, and Accounting would draft the $2,400 payment. That did happen, but the agents verified the data multiple times across the turn—checking rent four times and checking cash three times before the draft was submitted and approved.
For Ticket 103, the actual process split into two runs instead of our original single chain. We originally expected Boss to go to Inventory first, have Inventory pass directly to Accounting to calculate bulk discounts and restock limits, and then have Accounting hand off to Customer Service. In reality, Boss went to Accounting first to check pricing policy and margin room, then called Inventory to check physical stock, and then went back to Accounting to draft the 6-unit restock for $132 to stay within the $152 cash limit. Only after that purchase was human-approved did Run 2 begin, where Boss brought in Customer Service to draft the email explaining the 14 available hoodies and offering the Bulldog tee alternative.
Across all three tickets, the Boss ended up acting more like an active hub and coordinator who stayed involved throughout each step rather than simply assigning an initial task and stepping aside. We also saw significantly more tool usage than expected, especially with ticket listing, vendor checks, and alternative product searches.
What Would Have Been Simpler as One Agent with Tools - and Why
I think Ticket 102 would have been much simpler to handle with a single agent that had access to the necessary tools. The task itself was quite straightforward: check the lease terms, check available cash, and draft the payment for human approval.
Using three separate agents - Boss, Facilities, and Accounting - added additional handoffs without adding much additional reasoning. The agents checked rent four times and checked cash three times across different turns. Each handoff also required the system to pass along the relevant context and run another model call.
A single agent with tools such as check rent, check cash, and draft payment could have completed the same workflow much more efficiently. I think multi-agent delegation makes more sense when there are different priorities or trade-offs to balance, such as customer needs, inventory constraints, and financial considerations. For a simple administrative task like Ticket 102, however, one agent would have been more efficient.
Three New Problems the Current Agent Team Could Solve

1. Vendor price increase: When a vendor increases the price of an item, Inventory could identify which products are affected and check whether alternative vendors can supply them. Accounting could calculate the impact on margins and determine whether the company should raise its selling price. Boss could decide whether to switch vendors or change the customer price. Customer Service could prepare a response for customers asking about the price change.
2. Product is selling poorly: When a product has been sitting in inventory for a long time, Inventory could identify the quantity remaining and determine whether the product can be returned to the vendor. Accounting could calculate the current margin and determine how much of a discount can be offered without creating an excessive loss. Customer Service could draft a promotional message offering the product at the new price.
3. Out-of-stock substitutions: When a customer orders an item that is out of stock, Inventory could search for similar products in the same size, Accounting could check the price and margin and offer a discount since this is not the original product customer was looking for, and Customer Service could draft a message offering the customer an alternative with the discount sharing that since the original product is not available campus customs is offering a unique discount to the customer.

Three New Problems the Current Agent Team Could NOT Solve

1. Returns and damaged merchandise: The current system cannot handle customer returns, damaged products, or vendor credit requests. It mainly handles outgoing payments and does not have tools or processes for refunds, returned inventory, or vendor credits. This would require a Returns or Quality Assurance Agent with tools such as recording a return, removing damaged inventory, and requesting a vendor credit.
2. Customer invoicing and accounts receivable: The system cannot manage customers who purchase on credit because it does not have a way to create invoices, track accounts receivable, or record incoming customer payments. This would require a Billing and Receivables Agent.
3. Communication with the owner: The agents cannot communicate with the owner as of now. There can be an agent that communicates with the owner - drafting and sending emails and alerts to the owner and even taking owners input for very high level decisions like big discounts request from customers on bulk orders - these could be done via email where from an email the agent send an email to the owner sharing the situation and possible list of next steps and then the owner reply on that same email which the agent read and pass to the boss.
```

### Prompt 3

```text
fix the first phrase and second phrase should be who then talked to inventory
```

## Problem 11: Submit to GitHub

### Prompt 1

```text
we are moving to problem 11: submit to github: Push everything we did for homework 5 to a public GitHub repository. put the public repository link to output/github_url.txt. Do not push your real .env to the GitHub repo. Include both database files under data/ (the original and theworking copy).
```

### Prompt 2

```text
once you have pushed to github - ensure that everything has been pushed - all requirement files/codes so that when someone clone the repo they can easily run what we created here for homework 5 - save this prompt in AI_prompts.md befor the push to github
```
