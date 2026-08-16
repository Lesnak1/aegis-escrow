import { createClient, createAccount, type Address } from 'genlayer-js';
import { testnetBradbury, studionet } from 'genlayer-js/chains';

/**
 * AegisEscrow GenLayerJS Client Integration
 * Implements read (view), write (transactions), and transaction finality polling.
 */

export const AEGIS_ESCROW_ADDRESS: Address = '0x74e9242C875fcdd048E5BaB671902A29A5ddBA3c';

export function getGenLayerClient(privateKey?: `0x${string}`) {
  return createClient({
    chain: testnetBradbury,
    account: privateKey ? createAccount(privateKey) : createAccount(),
  });
}

/**
 * Creates an escrow agreement locking GEN funds.
 */
export async function createAgreement(
  client: ReturnType<typeof getGenLayerClient>,
  contractor: Address,
  depositGenAmount: number
) {
  const depositWei = BigInt(depositGenAmount) * BigInt(10 ** 18);

  const txHash = await client.writeContract({
    address: AEGIS_ESCROW_ADDRESS,
    functionName: 'create_agreement',
    args: [contractor],
    value: depositWei,
  });

  return txHash;
}

/**
 * Triggers multi-validator consensus adjudication on milestone deliverable.
 */
export async function submitAndAdjudicateMilestone(
  client: ReturnType<typeof getGenLayerClient>,
  agreementId: bigint,
  milestoneIdx: number,
  submissionNotes: string
) {
  const txHash = await client.writeContract({
    address: AEGIS_ESCROW_ADDRESS,
    functionName: 'submit_and_adjudicate_milestone',
    args: [agreementId, milestoneIdx, submissionNotes],
  });

  return txHash;
}

/**
 * Queries escrow agreement status (read-only view method).
 */
export async function getAgreement(
  client: ReturnType<typeof getGenLayerClient>,
  agreementId: bigint
) {
  const data = await client.readContract({
    address: AEGIS_ESCROW_ADDRESS,
    functionName: 'get_agreement',
    args: [agreementId],
  });

  return data;
}
