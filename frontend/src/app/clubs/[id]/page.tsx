import { ClubDetail } from "@/components/club-detail";

export default async function ClubPage({ params }: PageProps<"/clubs/[id]">) {
  const { id } = await params;
  return <ClubDetail clubId={id} />;
}