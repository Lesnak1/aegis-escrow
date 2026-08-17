import { createClient, createAccount, generatePrivateKey, type Address } from 'genlayer-js';
import { testnetBradbury, studionet, localnet } from 'genlayer-js/chains';

/**
 * AegisEscrow GenLayer Client Integration
 * Provides complete TypeScript bindings for all intelligent contract methods on GenLayer:
 * - create_agreement (Payable, locks GEN deposit)
 * - add_milestone (Defines milestone specifications & evidence URL)
 * - submit_and_adjudicate_milestone (Triggers multi-validator LLM consensus against live web evidence)
 * - refund_remaining (Reclaims unapproved remaining balance)
 * - get_agreement (Read-only view of agreement state)
 * - get_milestone (Read-only view of milestone adjudication metrics & scores)
 */

export const DEFAULT_AEGIS_ESCROW_ADDRESS: Address = '0x74e9242C875fcdd048E5BaB671902A29A5ddBA3c';

export interface MilestoneState {
  description: string;
  evidence_url: string;
  payout_amount: string;
  status: 'PENDING' | 'SUBMITTED' | 'APPROVED' | 'REVISION_REQUIRED' | 'REFUNDED';
  score_functional: number;
  score_criteria: number;
  score_quality: number;
  defect_severity: 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  adjudication_summary: string;
}

export interface EscrowAgreementState {
  client: string;
  contractor: string;
  total_locked: string;
  remaining_balance: string;
  is_active: boolean;
  milestone_count: number;
}

export type SupportedChain = 'testnetBradbury' | 'studionet' | 'localnet';

export function getChainConfig(chainType: SupportedChain = 'testnetBradbury') {
  switch (chainType) {
    case 'studionet':
      return studionet;
    case 'localnet':
      return localnet;
    case 'testnetBradbury':
    default:
      return testnetBradbury;
  }
}

export function getGenLayerClient(
  privateKey?: `0x${string}`,
  chainType: SupportedChain = 'testnetBradbury'
) {
  const account = privateKey ? createAccount(privateKey) : createAccount(generatePrivateKey());
  const chain = getChainConfig(chainType);

  return createClient({
    chain,
    account,
  });
}

/**
 * Creates an escrow agreement and locks deposited GEN funds.
 */
export async function createAgreement(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  contractorAddress: Address,
  depositGenAmount: string | number
): Promise<`0x${string}`> {
  const depositWei = BigInt(Math.floor(Number(depositGenAmount) * 1e18));

  const txHash = await client.writeContract({
    address: contractAddress,
    functionName: 'create_agreement',
    args: [contractorAddress],
    value: depositWei,
  });

  return txHash as `0x${string}`;
}

/**
 * Client defines and adds a verifiable milestone to the agreement.
 */
export async function addMilestone(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  agreementId: bigint | number,
  description: string,
  evidenceUrl: string,
  payoutGenAmount: string | number
): Promise<`0x${string}`> {
  const payoutWei = BigInt(Math.floor(Number(payoutGenAmount) * 1e18));

  const txHash = await client.writeContract({
    address: contractAddress,
    functionName: 'add_milestone',
    args: [BigInt(agreementId), description, evidenceUrl, payoutWei],
  });

  return txHash as `0x${string}`;
}

/**
 * Contractor submits milestone deliverable and triggers multi-validator LLM consensus.
 */
export async function submitAndAdjudicateMilestone(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  agreementId: bigint | number,
  milestoneIdx: number,
  submissionNotes: string
): Promise<`0x${string}`> {
  const txHash = await client.writeContract({
    address: contractAddress,
    functionName: 'submit_and_adjudicate_milestone',
    args: [BigInt(agreementId), milestoneIdx, submissionNotes],
  });

  return txHash as `0x${string}`;
}

/**
 * Client requests a refund of the remaining unapproved escrow balance.
 */
export async function refundRemaining(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  agreementId: bigint | number
): Promise<`0x${string}`> {
  const txHash = await client.writeContract({
    address: contractAddress,
    functionName: 'refund_remaining',
    args: [BigInt(agreementId)],
  });

  return txHash as `0x${string}`;
}

/**
 * Queries escrow agreement state from contract storage.
 */
export async function getAgreement(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  agreementId: bigint | number
): Promise<EscrowAgreementState> {
  const data = await client.readContract({
    address: contractAddress,
    functionName: 'get_agreement',
    args: [BigInt(agreementId)],
  });

  return data as unknown as EscrowAgreementState;
}

/**
 * Queries milestone state and multi-validator adjudication verdict from contract storage.
 */
export async function getMilestone(
  client: ReturnType<typeof getGenLayerClient>,
  contractAddress: Address,
  agreementId: bigint | number,
  milestoneIdx: number
): Promise<MilestoneState> {
  const data = await client.readContract({
    address: contractAddress,
    functionName: 'get_milestone',
    args: [BigInt(agreementId), milestoneIdx],
  });

  return data as unknown as MilestoneState;
}

/**
 * Waits for transaction finality and consensus receipt on GenLayer.
 */
export async function waitForTransactionReceipt(
  client: ReturnType<typeof getGenLayerClient>,
  hash: `0x${string}`
) {
  return await client.waitForTransactionReceipt({ hash });
}
